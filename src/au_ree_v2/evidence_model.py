"""Versioned, relational reading model of facts in the single evidence store.

Each source edition and observation stays addressable. These views enumerate evidence;
they do not perform Census selection, assign ownership or add quantities across rows.
"""
import json

SCHEMA_VERSION = 1
RESOURCE_CLASSES = {'MEASURED','INDICATED','INFERRED','MEASURED_INDICATED',
                    'INDICATED_INFERRED','MEASURED_INDICATED_INFERRED'}


def compatible_resource_context(rows):
    """Detect explicit contradictions inside an otherwise matching source statement.

    Missing metadata permits no new join; callers already match project, document,
    statement, date and scope. An expressly different basis blocks that join.
    """
    cutoffs = set()
    categories = set()
    for row in rows:
        raw = json.loads(row.get('raw') or '{}')
        kind = raw.get('resource_type') or raw.get('statement_kind')
        if kind and str(kind).upper().replace(' ', '_') not in ('RESOURCE', 'MINERAL_RESOURCE', 'MRE'):
            return False
        material = raw.get('material_basis')
        if material and row['variable'] in ('ore_mt','grade','contained_treo_kt'):
            # These variables supply the bulk resource pair. HM-hosted oxides
            # enter separately with reviewed HM mass and a verified conversion.
            if not str(material).upper().startswith(('WHOLE_ORE','BULK_ORE','RESOURCE_BULK_ORE',
                                                     'RESOURCE_ORE','RESOURCE_CONTAINED')):
                return False
        cutoff = raw.get('cutoff_grade')
        if cutoff is None:
            cutoff = raw.get('cutoff')
        if cutoff is None:
            cutoff = (raw.get('review_contract') or {}).get('cutoff')
        if cutoff is not None and cutoff != '':
            cutoffs.add(json.dumps(cutoff, sort_keys=True, ensure_ascii=False))
        category = row.get('category')
        if category and (category.removesuffix('_TOTAL') in RESOURCE_CLASSES or
                         row['variable'] in ('ore_mt','grade','contained_treo_kt') and category != 'NOT_APPLICABLE'):
            categories.add(category)
    return len(cutoffs) <= 1 and len(categories) <= 1

# Preserve malformed legacy payloads in observations. Unavailable structured metadata
# stays unknown rather than making an older database impossible to query or migrate.
RESOURCE_FACTS = """
WITH evidence AS (
    SELECT o.*, s.publication_date, s.acquired_at, s.source_key,
           CASE WHEN json_valid(o.raw) THEN o.raw ELSE '{}' END AS payload
    FROM observations o JOIN sources s ON s.sha=o.source_sha
    WHERE o.variable IN ('ore_mt','grade','contained_treo_kt','magnet_reo_share_pct')
       OR o.variable GLOB 'reported_*' OR o.variable GLOB 'official_batch_*'
       OR o.raw LIKE '%material_basis%'
), criteria AS (
    SELECT e.*, coalesce(json_extract(payload,'$.material_basis'),
                         json_extract(payload,'$.raw.reviewed_observation.material_basis')) AS material_basis,
           json_extract(payload,'$.raw.review_contract') AS review_contract,
           coalesce(json_extract(payload,'$.resource_type'),json_extract(payload,'$.statement_kind'),
                    CASE WHEN variable GLOB 'official_batch_rv_*' THEN 'ORE_RESERVE'
                         WHEN variable GLOB 'official_batch_res_*' THEN 'MINERAL_RESOURCE' END) AS declared_kind,
           coalesce(json_extract(payload,'$.cutoff_grade'),json_extract(payload,'$.cutoff'),
                    json_extract(payload,'$.raw.review_contract.cutoff')) AS cutoff_grade
    FROM evidence e
), classified AS (
    SELECT c.*, CASE WHEN declared_kind IS NOT NULL THEN declared_kind
                     WHEN variable IN ('ore_mt','grade','contained_treo_kt','magnet_reo_share_pct')
                       OR review_contract IS NOT NULL OR variable GLOB 'reported_resource_*'
                       THEN 'RESOURCE_CONTEXT' ELSE 'UNSPECIFIED' END AS statement_kind
    FROM criteria c
    WHERE variable IN ('ore_mt','grade','contained_treo_kt','magnet_reo_share_pct')
       OR variable GLOB 'official_batch_*' OR variable GLOB 'reported_resource_*'
       OR material_basis GLOB 'RESOURCE_*' OR material_basis GLOB 'HEAVY_MINERAL_*'
       OR (variable GLOB 'reported_*' AND review_contract IS NOT NULL AND review_contract <> '{}')
)
SELECT c.*,
       json_array(entity_id,source_sha,statement_id,scope,effective_date,statement_kind,cutoff_grade)
         AS source_statement_key,
       coalesce(json_extract(payload,'$.reporting_standard'),
                json_extract(review_contract,'$.reporting_standard')) AS reporting_standard,
       coalesce(json_extract(payload,'$.effective_date_role'),json_extract(payload,'$.date_role'),
                json_extract(review_contract,'$.effective_date_role')) AS date_role,
       coalesce(json_extract(payload,'$.effective_date_precision'),
                json_extract(review_contract,'$.date_precision')) AS declared_date_precision,
       coalesce(json_extract(payload,'$.original_estimate_date'),json_extract(payload,'$.resource_effective_period'),
                json_extract(payload,'$.resource_date')) AS original_estimate_period,
       coalesce(json_extract(payload,'$.original_token'),json_extract(payload,'$.original_reported_value'),
                json_extract(payload,'$.original_value'),json_extract(payload,'$.original_tokens')) AS reported_token,
       coalesce(json_extract(payload,'$.original_reported_unit'),json_extract(payload,'$.original_unit'),
                json_extract(payload,'$.cell_binding.original_unit')) AS reported_unit,
       coalesce(json_extract(payload,'$.composition_denominator_basis'),json_extract(payload,'$.source_total_basis'))
         AS denominator_basis,
       coalesce(json_extract(payload,'$.transform'),json_extract(payload,'$.basis_transform'),
                json_extract(payload,'$.species_conversion'),
                json_extract(payload,'$.raw.reviewed_observation.transform'),
                json_extract(payload,'$.raw.reviewed_observation.species_conversion')) AS source_transform,
       coalesce(json_extract(payload,'$.rounding_half_width'),json_extract(payload,'$.raw.reviewed_observation.rounding_half_width'))
         AS rounding_half_width,
       coalesce(json_extract(payload,'$.supersedes_statement_id'),json_extract(payload,'$.original_statement_id'))
         AS referenced_statement_label
FROM classified c
"""

# The original key explicitly includes only source-declared cutoff. An unspecified
# cutoff or kind cannot silently create equivalence with a disclosed one. Presentation
# groups spanning proven equivalent versions are recorded by the run's selector.
MODEL_VIEWS = {
    "resource_statement_facts": RESOURCE_FACTS,
    "resource_statement_editions": """
        SELECT DISTINCT source_statement_key,entity_id,source_sha,source_key,statement_id,
               scope,effective_date,statement_kind,cutoff_grade,publication_date,acquired_at
        FROM resource_statement_facts""",
    "relation_chronology": """
        SELECT r.relation_id,r.parent_id,r.child_id,r.relation,r.source_sha,r.locator,
               r.effective_date AS legacy_reference_date,
               CASE
                 WHEN r.relation IN ('RESOURCE_SUMMARY_FOR_NATIVE_PROJECT',
                      'REPRESENTATIVE_RESOURCE_LOCATION_SITE_NOT_RESOURCE_EXTENT') THEN 'SOURCE_PUBLICATION'
                 WHEN r.relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE' THEN 'SOURCE_AVAILABILITY'
                 WHEN r.relation IN ('LISTED_AS_PROJECT_NOT_DEPOSIT_EQUIVALENCE',
                      'LISTED_IN_NATIONAL_PROSPECTUS') THEN 'LISTING_REFERENCE'
                 WHEN r.relation='SAME_NATIVE_GA_ENO_SOURCE_ONLY' THEN 'NATIVE_ID_MATCH_POLICY'
                 WHEN r.effective_date='2026-11-03' THEN 'LEGACY_REFERENCE_UNVERIFIED'
                 ELSE 'UNCLASSIFIED_REFERENCE' END AS reference_date_role,
               NULL AS relationship_effective_date,
               CASE WHEN r.relation='HAS_TECHNICALLY_DOCUMENTED_RESOURCE_SCOPE' AND json_valid(rec.raw)
                    THEN coalesce(json_extract(rec.raw,'$.original_estimate_date'),
                                  json_extract(rec.raw,'$.resource_effective_period'),
                                  json_extract(rec.raw,'$.raw.review_contract.effective_date'))
                    END AS resource_estimate_period,
               s.publication_date AS source_publication,s.acquired_at AS source_acquired_at
        FROM relations r JOIN sources s ON s.sha=r.source_sha
        LEFT JOIN records rec ON rec.entity_id=r.child_id AND rec.source_sha=r.source_sha""",
    "technical_study_context": """
        SELECT c.case_id,c.project_id,c.source_sha,c.scope,c.effective_date,c.endpoint,c.element,c.scale,
               c.stage,c.status, json_extract(c.raw,'$.recovery_feed') AS feed,
               json_extract(c.raw,'$.process') AS process,
               json_extract(c.raw,'$.parameters') AS reported_parameters,
               json_extract(c.raw,'$.locator') AS locator
        FROM study_cases c WHERE json_valid(c.raw)""",
    "company_role_disclosures": """
        SELECT obs_id,entity_id,source_sha,scope,locator,effective_date AS disclosure_reference_date,
               CASE WHEN variable='government_authorisedholdername' THEN 'REGISTERED_TENURE_HOLDER'
                    WHEN json_extract(raw,'$.column')='ASX代碼' THEN 'EXCHANGE_CODE'
                    WHEN json_extract(raw,'$.column')='未上市公司' THEN 'LISTING_STATUS'
                    ELSE coalesce(json_extract(raw,'$.company_role'),'REPORTED_DEVELOPER_LABEL') END AS role,
               coalesce(json_extract(raw,'$.original_value'),json_extract(raw,'$.value')) AS reported_value,
               json_extract(raw,'$.holding_pct') AS holding_pct,json_extract(raw,'$.valid_from') AS valid_from,
               json_extract(raw,'$.valid_to') AS valid_to,status
        FROM observations WHERE json_valid(raw) AND (variable='government_authorisedholdername'
             OR (variable='project_attribute' AND json_extract(raw,'$.column') IN ('開發商','ASX代碼','未上市公司')))""",
    "product_disclosures": """
        SELECT obs_id,entity_id,source_sha,scope,locator,effective_date AS disclosure_reference_date,
               json_extract(raw,'$.value') AS source_product,
               CASE WHEN json_type(raw,'$.engineering_forecast')='object' THEN 'STUDY_FORECAST'
                    ELSE coalesce(json_extract(raw,'$.production_role'),'SOURCE_LABEL_ROLE_UNRESOLVED') END AS production_role,
               json_extract(raw,'$.engineering_forecast.endpoint') AS endpoint,
               json_extract(raw,'$.engineering_forecast.scale') AS engineering_scale,
               json_extract(raw,'$.engineering_forecast.selected_scenario') AS scenario,
               json_extract(raw,'$.engineering_forecast.parameters') AS published_parameters,
               json_extract(raw,'$.source_stated_annual') AS annual_statement,status
        FROM observations WHERE variable='project_attribute' AND json_valid(raw)
          AND json_extract(raw,'$.column')='產品/產出'""",
}


def install_model(db, *, temporary=False):
    """Install the same projections persistently or for a read-only v0 connection."""
    for name, query in MODEL_VIEWS.items():
        # Identifiers are module constants, never external data.
        kind = 'TEMP VIEW IF NOT EXISTS' if temporary else 'VIEW'
        db.execute(f'CREATE {kind} {name} AS {query}')


def migrate_evidence_model(db):
    """Upgrade legacy user_version=0 in place; schema and version commit atomically."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise ValueError(f'Unsupported evidence schema version {version}')
    # Re-read under the lock: two concurrent upgraders can both initially see v0.
    db.execute('BEGIN IMMEDIATE')
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            install_model(db)
            # SQLite postpones view resolution until use. Catch missing dependencies
            # now, before declaring a successful migration of an incomplete schema.
            for name in MODEL_VIEWS:
                db.execute(f'SELECT * FROM {name} LIMIT 0')
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        elif version != SCHEMA_VERSION:
            raise ValueError(f'Unsupported evidence schema version {version}')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def ensure_read_model(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 0:
        install_model(db, temporary=True)
    elif version != SCHEMA_VERSION:
        raise ValueError(f'Unsupported evidence schema version {version}')
