"""Read surrendered one-minute title blocks from the map attached to an NT mining notice."""
from datetime import date
from hashlib import sha256
from pathlib import Path
import re

import pymupdf
from pyproj import Geod
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from .store import filehash
from .tenement_geometry import summary_tenement_centroid


# Reviewed dimensions, labelled meridians/parallels (arcminutes E/S) and their pixel centres.
# The exact decoded map hash locks the labels and axes to their map, including interior gaps.
# Each panel's legal text is directly above its map in MN101/24, p1.
NOTICE_SHA = '773be501babb87dc78ba444e8fc0d914d7b0fb0df4333679e3ef016c4a7a5b49'
GRIDS = {
    '33000': ('3d87bc6fc1e0113ada5378b2a491b6818b9c674026fd391318d987e2f7846fd1',
              (133*60+18, 22*60+45, 12, 24), (160, 99, 333, 474), '274/24', '09 August 2024', 57, 180.13),
    '33004': ('cb482e476b408ab71997dd442ae044dc20f51904509ab4c54595dec98189da1c',
              (132*60+14, 23*60+4, 31, 4), (65, 261, 439, 314), '275/24', '05 August 2024', 122, 385.49),
    '33006': ('72011b181073b7aadab8222e7243f2415039cea2836dbd0ca15daf2217d31be4',
              (133*60+14, 23*60+16, 19, 11), (69, 173, 427, 400), '277/24', '09 August 2024', 110, 346.90),
}


def read_graticule(pixmap, axes, image_grid):
    """Pair thick boundary crossings on the centreline of each one-minute row."""
    west, north, cols, rows = axes
    x0, y0, x1, y1 = image_grid
    if (pixmap.width, pixmap.height, pixmap.n) != (550, 550, 3):
        raise ValueError('NT_MINING_NOTICE_MAP_FORMAT')
    pixels = pixmap.samples
    strips = []
    count = 0
    for j in range(rows):
        y = round(y0 + (j + .5) * (y1 - y0) / rows)
        crossings = []
        for i in range(cols + 1):
            x = round(x0 + i * (x1 - x0) / cols)
            # The axes are one pixel wide. Title boundary lines are three black pixels.
            width = sum(pixels[3 * (y * pixmap.width + x + offset)] < 150 for offset in range(-3, 4))
            if width >= 2:
                crossings.append(i)
        if len(crossings) % 2:
            raise ValueError('NT_MINING_NOTICE_OPEN_RING')
        for left, right in zip(crossings[::2], crossings[1::2]):
            strips.append(box((west + left) / 60, -(north + j + 1) / 60,
                              (west + right) / 60, -(north + j) / 60))
            count += right - left
    shape = unary_union(strips).simplify(0)
    if shape.is_empty or not shape.is_valid:
        raise ValueError('NT_MINING_NOTICE_EMPTY_OR_INVALID')
    return shape, count


def statutory_extent(source, sources, binding, row, cutoff, limit_m):
    """Match the legal map, dated historical project scope and native block count before projection."""
    title = binding['licence']
    region = sources.get(binding['report_sha256'])
    if (not cutoff or source.get('kind') != 'pdf' or source.get('sha256') != NOTICE_SHA
            or source.get('publication_date') != '2024-08-22' or source['publication_date'] > cutoff
            or not region or region['kind'] != 'pdf' or not region.get('publication_date')
            or region['publication_date'] > cutoff
            or binding['project_name'] != row['專案名稱'] or binding['project_id'] != row['專案ID']
            or not re.search(r'\bEL' + re.escape(title) + r'\b', row['專案名稱'])
            or row['開發商'] != 'URO Corporation Pty Ltd' or title not in GRIDS):
        return None
    source_path, report_path = Path(source['resolved_path']), Path(region['resolved_path'])
    if filehash(source_path) != NOTICE_SHA or filehash(report_path) != binding['report_sha256']:
        return None
    image_hash, axes, grid, notice, ceased, nblocks, area = GRIDS[title]
    with pymupdf.open(report_path) as report:
        page_number = binding['report_page']
        if not isinstance(page_number, int) or not 1 <= page_number <= len(report):
            return None
        text = ' '.join(report[page_number - 1].get_text().split()).casefold()
    relinquished = 'relinquished area' in text or 'area relinquished' in text
    retained = 'retained area' in text or 'area retained' in text
    if not (relinquished and retained and all(marker in text for marker in
            ('el' + title, f'{nblocks} blocks', '22nd august 2024'))):
        return None
    with pymupdf.open(source_path) as doc:
        page = doc[0]
        if '22 August 2024' not in page.get_text() or 'MN101/24' not in page.get_text():
            return None
        for item in page.get_images():
            ref, _, width, height = item[:4]
            if (width, height) != (550, 550):
                continue
            pixels = pymupdf.Pixmap(doc, ref)
            if sha256(pixels.samples).hexdigest() != image_hash:
                continue
            positions = page.get_image_rects(ref)
            if len(positions) != 1:
                return None
            loc = positions[0]
            text = ' '.join(page.get_textbox(pymupdf.Rect(loc.x0-42, loc.y0-80, loc.x1+22, loc.y0+2)).split())
            label = page.get_textbox(pymupdf.Rect(loc.x0-42, loc.y1, loc.x0+15, loc.y1+18)).strip()
            if label != notice or not all(word in text for word in ('LAND CEASING TO BE A MINERAL TITLE AREA',
                    'Exploration Licence ' + title, ceased, f'{nblocks} Blocks, {area:.2f} km²',
                    '100% URO CORPORATION PTY LTD', '653 927 998')):
                return None
            shape, blocks = read_graticule(pixels, axes, grid)
            if blocks != nblocks:
                return None
            break
        else:
            return None
    result = summary_tenement_centroid([dict(geometry=mapping(shape))], 4283, limit_m)
    result.update(dataset=source['key'], notice_id=notice, notice_sha256=NOTICE_SHA, physical_page=1,
                  map_rgb_sha256=image_hash, tenement_ids=['EL'+title], block_count=blocks,
                  reported_km2=area, geodesic_km2=abs(Geod(ellps='GRS80').geometry_area_perimeter(shape)[0])/1e6,
                  effective_date=date(2024, 8, int(ceased[:2])).isoformat(),
                  publication_date=source['publication_date'], holder='URO Corporation Pty Ltd',
                  scope_report_sha256=binding['report_sha256'], scope_report_page=binding['report_page'],
                  meaning='HISTORICAL_RELINQUISHED_TENEMENT_PORTION_NOT_RESOURCE_BOUNDARY')
    return result
