"""A bounded, rendered-page benchmark; never an input to evidence ingestion."""
import json
import sys
from pathlib import Path
from collections import Counter
from au_ree_v2.acquisition import select_snapshots


def evaluate(root):
    root=Path(root);snapshots=select_snapshots(root,'2026-11-03')
    artifacts={s['source_sha256']:json.loads((root/s['path']).read_text(encoding='utf-8'))
               for s in snapshots if s['kind']=='document_extraction'}
    by_key={s['key']:s for s in snapshots}
    # Ground truth is used exclusively for evaluation. These selected cells were
    # checked against rendered originals; there is no corpus-wide recall claim.
    gold=[('mt_weld_2024',2,'Total',{'ore_mt':106.6,'grade':4.1,'contained_treo_kt':4389.}),
          ('yttria_maiden2024',2,'Total',{'ore_mt':15.,'grade':490.,'MREO':110.,'LREO':220.,'HREO':270.,
                                      'Pr6O11':15.,'Nd2O3':64.,'Dy2O3':24.,'Tb4O7':3.7,'Sc2O3':68.,'U':.6,'Th':1.}),
          ('discovery_asra_primary_met_alternative_530e7a5f3d94',2,'Avg:HCl',
           {'TREO':66.,'MREO':78.,'Pr6O11':85.,'Nd2O3':85.,'Tb4O7':69.,'Dy2O3':62.,'Sc2O3':23.}),
          ('discovery_asra_primary_met_alternative_530e7a5f3d94',2,'Avg:Sulfuric and Magnesium Chloride',
           {'TREO':49.,'MREO':61.,'Pr6O11':67.,'Nd2O3':67.,'Tb4O7':52.,'Dy2O3':46.,'Sc2O3':29.}),
          # Difficult layouts remain held out; misses must remain in the metric.
          ('koppamurra_pfs2026',8,'Total',{'ore_mt':243.,'grade':751.}),
          ('browns_range_2025',54,'Total',{'ore_mt':7.3,'grade':.96})]
    tp=fp=fn=located=unit_correct=0;cells=[]
    for key,page,row_label,expected in gold:
        data=artifacts[by_key[key]['sha256']]
        rows=[c for c in data['candidates'] if c['physical_page']==page and c['kind'] in ('RESOURCE_TABLE_TOTAL','LEACH_TABLE_ROW') and not c['issues']]
        if row_label.startswith('Avg:'):
            reagent=row_label.split(':',1)[1]
            rows=[c for c in rows if c.get('sample_id')=='Avg' and c.get('reagent')==reagent]
        found={}
        if len(rows)==1:
            found={**rows[0]['values'],**{e['label']:e['value'] for e in rows[0].get('extra_values',[])}}
        for variable,value in expected.items():
            actual=found.get(variable)
            expected_unit='%' if row_label.startswith('Avg:') else ('Mt' if variable=='ore_mt' else 'kt TREO' if variable=='contained_treo_kt' else '%' if key=='mt_weld_2024' else 'ppm')
            actual_unit=(rows[0].get('unit') or rows[0].get('units',{}).get(variable) or next((e['unit'] for e in rows[0].get('extra_values',[]) if e['label']==variable),None)) if len(rows)==1 else None
            if actual==value and actual_unit==expected_unit:
                tp+=1;unit_correct+=1;located+=bool(rows[0]['physical_page'] and rows[0]['source_sha256']);status='EXACT'
            elif actual is None:fn+=1;status='NOT_VALIDATED_LAYOUT_OR_SCOPE'
            else:fp+=1;fn+=1;status='VALUE_OR_COLUMN_ERROR'
            cells.append(dict(source_key=key,physical_page=page,row_label=row_label,variable=variable,expected=value,actual=actual,expected_unit=expected_unit,actual_unit=actual_unit,status=status))
    return dict(version='rendered-cell-benchmark-v1',scope='SELECTED_CELLS_SIX_TABLE_SCOPES_FIVE_DOCUMENTS_NOT_CORPUS_WIDE',
                cells=len(cells),true_positive=tp,false_positive=fp,false_negative=fn,
                precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                unit_contract='Mt_or_percent_or_ppm_as_printed; element columns kept separate',
                source_locator_completeness_of_validated=located/tp if tp else None,
                unit_accuracy_of_validated=unit_correct/tp if tp else None,results=cells)


if __name__=='__main__':
    result=evaluate('.')
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
