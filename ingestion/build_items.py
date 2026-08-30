"""Build the item catalogue from the National List of Essential Medicines 2022.

The whole NLEM is loaded, not a shortlist. Voice, chat and barcode capture all
match against the full catalogue, so "recognises the complete National List of
Essential Medicines" is a claim the product can actually stand behind.

Forecasting is a narrower question. Generating usage and training ARIMA for
~380 items across ~200 facilities would be ~76,000 series and ~28M rows, most of
it for medicines a PHC never dispenses and for which no demand signal exists.
So `is_forecast_item` marks a curated subset: every item with a genuine HMIS
demand driver, plus the highest-volume PHC staples. The defensible position, and
the way a real rollout would work, is: **every essential medicine is tracked;
forecasting is active where sufficient signal exists.**

Run:
    python -m ingestion.build_items --dry-run
    python -m ingestion.build_items
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from google.cloud import bigquery

from ingestion.atc_map import atc_for, normalise
from ingestion.parse_nlem import parse_nlem

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
TABLE = f"{PROJECT}.{DATASET}.items"

# ---------------------------------------------------------------------------
# VEN classification — WHO / MoHFW practice
# ---------------------------------------------------------------------------
# Vital      life-saving; a stock-out causes death or serious harm
# Essential  effective against significant but not immediately life-threatening
#            illness
# Desirable  minor illness, or adequate alternatives exist
#
# Applied as an NLEM-section default with explicit per-medicine overrides. The
# section default is the honest starting point — NLEM sections are already
# organised by clinical purpose — and the overrides carry the cases where a
# section mixes criticality.
VITAL_SECTIONS = {
    1,   # Anaesthetics
    3,   # Antiallergics and medicines used in anaphylaxis
    4,   # Antidotes
    9,   # Blood products and plasma substitutes
    19,  # Immunologicals (vaccines)
    20,  # Neonatal care
    22,  # Oxytocics and antioxytocics
    25,  # Fluids and electrolytes
    27,  # COVID-19
}
DESIRABLE_SECTIONS = {
    11,  # Dermatological (topical)
    12,  # Diagnostic agents
    16,  # Ear, nose and throat
    26,  # Vitamins and minerals
}

VITAL_OVERRIDES = {
    "adrenaline", "atropine", "naloxone", "oxytocin", "magnesium sulphate",
    "oral rehydration salts", "insulin", "ceftriaxone", "benzylpenicillin",
    "snake venom antiserum", "salbutamol", "glyceryl trinitrate",
    "phenobarbitone", "diazepam", "phenytoin", "furosemide", "dopamine",
    "dobutamine", "noradrenaline", "hydrocortisone", "isoniazid", "rifampicin",
    "pyrazinamide", "ethambutol", "artesunate", "artemether + lumefantrine",
    "chloroquine", "zidovudine", "lamivudine", "dolutegravir", "nevirapine",
    "amphotericin b", "vancomycin", "meropenem", "streptokinase",
    "tranexamic acid", "phytomenadione", "misoprostol", "methylergometrine",
}
DESIRABLE_OVERRIDES = {
    "calamine", "white petrolatum", "coal tar", "carboxymethylcellulose",
    "benzoyl peroxide", "salicylic acid", "betahistine", "xylometazoline",
}

# ---------------------------------------------------------------------------
# Forecast subset — item -> HMIS indicator in `demand_reference`
# ---------------------------------------------------------------------------
# The 11 indicators actually available are the only permitted values. An item
# is only given a driver where the clinical link is direct: the indicator counts
# the patients who consume that medicine.
FORECAST_DRIVERS: dict[str, str] = {
    # Malaria — RDT and microscopy positives drive antimalarial consumption
    "Chloroquine": "Malaria",
    "Primaquine": "Malaria",
    "Artemether (A) + Lumefantrine (B)": "Malaria",
    "Artesunate (A) + Sulphadoxine - Pyrimethamine (B)": "Malaria",

    # Hypertension outpatients drive antihypertensive consumption
    "Amlodipine": "Outpatient - Hypertension",
    "Enalapril": "Outpatient - Hypertension",
    "Hydrochlorothiazide": "Outpatient - Hypertension",
    "Telmisartan": "Outpatient - Hypertension",

    # Diabetes outpatients drive oral hypoglycaemics and insulin
    "Metformin": "Outpatient - Diabetes",
    "Glimepiride": "Outpatient - Diabetes",
    "Insulin (Soluble)": "Outpatient - Diabetes",

    # Epilepsy outpatients drive anticonvulsants
    "Phenytoin": "Outpatient - Epilepsy",
    "Carbamazepine": "Outpatient - Epilepsy",
    "Sodium Valproate": "Outpatient - Epilepsy",
    "Phenobarbitone": "Outpatient - Epilepsy",

    # Mental illness outpatients drive psychotropics
    "Amitriptyline": "Outpatient - Mental illness",
    "Fluoxetine": "Outpatient - Mental illness",
    "Haloperidol": "Outpatient - Mental illness",
    "Risperidone": "Outpatient - Mental illness",

    # Ophthalmic outpatients drive topical eye medicines
    "Timolol": "Outpatient - Ophthalmic Related",

    # Dental outpatients drive oral antiseptic use
    "Chlorhexidine": "Outpatient - Dental",

    # Acute heart disease outpatients drive antiplatelets, nitrates, statins
    "Acetylsalicylic acid": "Outpatient - Acute Heart Diseases",
    "Glyceryl trinitrate": "Outpatient - Acute Heart Diseases",
    "Atorvastatin": "Outpatient - Acute Heart Diseases",

    # Stroke outpatients drive secondary-prevention antiplatelets
    "Clopidogrel": "Outpatient - Stroke (Paralysis)",

    # Childhood disease counts drive paediatric staples
    "Oral rehydration salts": "Childhood Diseases",
    "Zinc Sulphate": "Childhood Diseases",
    "Amoxicillin": "Childhood Diseases",
    "Vitamin A": "Childhood Diseases",
    "Albendazole": "Childhood Diseases",

    # Inpatient counts drive injectables and IV fluids
    "Ceftriaxone": "Inpatient counts",
    "Ringer lactate": "Inpatient counts",
    "Sodium chloride": "Inpatient counts",
}

# Forecast items with NO honest HMIS driver. These are high-volume PHC staples
# that must be forecast, but `demand_reference` contains no indicator that
# counts the patients who consume them. They get a flat seasonal baseline —
# explicitly, rather than being quietly attached to a loosely related indicator.
FLAT_BASELINE_ITEMS: dict[str, str] = {
    "Paracetamol":
        "Universal antipyretic and analgesic. Consumption tracks total "
        "outpatient attendance, and HMIS publishes no total-OPD indicator — "
        "only disease-specific columns.",
    "Ibuprofen":
        "General analgesic, mostly musculoskeletal pain. No HMIS indicator "
        "counts that presentation.",
    "Ferrous Salt (A)+ Folic acid (B)":
        "Driven by the antenatal and anaemia control programmes, not by any "
        "outpatient morbidity column present in demand_reference.",
    "Oxytocin":
        "Driven by the number of deliveries. HMIS reports delivery counts, but "
        "they are not among the 11 indicators parsed into demand_reference.",
    "Magnesium sulphate":
        "Driven by eclampsia and pre-eclampsia cases during delivery. Same gap "
        "as Oxytocin.",
    "Salbutamol":
        "Driven by asthma and COPD presentations. demand_reference holds no "
        "respiratory outpatient indicator.",
}

# ---------------------------------------------------------------------------
# Spoken variants — how health workers actually say these names
# ---------------------------------------------------------------------------
SPOKEN_VARIANTS: dict[str, list[str]] = {
    "Paracetamol": ["paracetamol", "para", "pcm", "crocin", "dolo",
                    "bukhar ki goli", "पैरासिटामोल"],
    "Amoxicillin": ["amoxicillin", "amoxy", "amox", "मोक्सिसिलिन"],
    "Oral rehydration salts": ["ors", "o r s", "oral rehydration", "ors packet",
                               "ors ka packet", "जीवन रक्षक घोल"],
    "Zinc Sulphate": ["zinc", "zinc tablet", "जिंक"],
    "Ferrous Salt (A)+ Folic acid (B)": ["iron folic acid", "ifa", "iron tablet",
                                         "ifa tablet", "khoon ki goli", "आयरन"],
    "Metformin": ["metformin", "glycomet", "sugar ki goli", "मेटफॉर्मिन"],
    "Amlodipine": ["amlodipine", "amlo", "bp ki goli", "एम्लोडिपिन"],
    "Chloroquine": ["chloroquine", "cq", "malaria ki goli", "क्लोरोक्वीन"],
    "Ceftriaxone": ["ceftriaxone", "cef", "injection ceftriaxone", "सेफ्ट्रिएक्सोन"],
    "Ibuprofen": ["ibuprofen", "brufen", "dard ki goli", "आइबुप्रोफेन"],
    "Salbutamol": ["salbutamol", "asthalin", "inhaler", "साल्बुटामोल"],
    "Phenytoin": ["phenytoin", "eptoin", "मिर्गी की गोली"],
    "Oxytocin": ["oxytocin", "pitocin", "ऑक्सीटोसिन"],
    "Vitamin A": ["vitamin a", "vit a", "vitamin a solution", "विटामिन ए"],
    "Albendazole": ["albendazole", "albenda", "pet ke keede ki goli"],
    "Insulin (Soluble)": ["insulin", "regular insulin", "इंसुलिन"],
    "Acetylsalicylic acid": ["aspirin", "asa", "ecosprin", "एस्पिरिन"],
    "Atorvastatin": ["atorvastatin", "atorva", "lipitor"],
    "Chlorhexidine": ["chlorhexidine", "mouthwash", "hexidine"],
    "Ringer lactate": ["ringer lactate", "rl", "ringer", "iv fluid"],
    "Sodium chloride": ["normal saline", "ns", "saline", "sodium chloride"],
}

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
UNIT_RULES = [
    (r"\btablet\b", "tablet"),
    (r"\bcapsule\b", "capsule"),
    (r"\bsachet\b", "sachet"),
    (r"powder for injection|\binjection\b|\bvial\b|\bampoule\b", "vial"),
    (r"\bdrops?\b|eye drop|ear drop", "bottle"),
    (r"oral liquid|\bsyrup\b|\bsuspension\b|\bsolution\b|\belixir\b", "bottle"),
    (r"\bcream\b|\bointment\b|\bgel\b|\bjelly\b|\bpaste\b|\blotion\b", "tube"),
    (r"\bpessary\b|\bsuppository\b", "unit"),
    (r"\binhaler\b|\brotacap\b|\brespirator\b", "inhaler"),
    (r"\bpatch\b", "patch"),
    (r"\bpowder\b|\bcrystals?\b|\bgranules\b", "sachet"),
]


def infer_unit(dosage_forms: str) -> str:
    text = (dosage_forms or "").lower()
    for pattern, unit in UNIT_RULES:
        if re.search(pattern, text):
            return unit
    return "unit"


def classify_ven(name: str, section_no: str) -> str:
    key = normalise(name)
    if key in VITAL_OVERRIDES:
        return "Vital"
    if key in DESIRABLE_OVERRIDES:
        return "Desirable"
    try:
        section = int(section_no)
    except (TypeError, ValueError):
        return "Essential"
    if section in VITAL_SECTIONS:
        return "Vital"
    if section in DESIRABLE_SECTIONS:
        return "Desirable"
    return "Essential"


def make_item_id(name: str, taken: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalise(name)).strip("-").upper()[:44]
    slug = slug or "ITEM"
    candidate, suffix = slug, 2
    while candidate in taken:
        candidate = f"{slug}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


# ---------------------------------------------------------------------------
def build_items() -> list[dict]:
    parsed = parse_nlem()

    # The conversion contains case-variant duplicates ("Sodium Valproate" and
    # "Sodium valproate"). Collapse them, keeping the first spelling and
    # merging the dosage forms.
    merged: dict[str, dict] = {}
    for row in parsed.to_dict("records"):
        key = normalise(row["medicine"])
        if not key:
            continue
        if key in merged:
            existing = merged[key]
            extra = row["dosage_forms"]
            if extra and extra not in existing["dosage_forms"]:
                existing["dosage_forms"] = (
                    f"{existing['dosage_forms']} | {extra}".strip(" |")
                )
            if "P" in row["level_of_care"]:
                existing["level_of_care"] = row["level_of_care"]
            continue
        merged[key] = dict(row)

    taken: set[str] = set()
    items: list[dict] = []
    for row in merged.values():
        name = row["medicine"]
        driver = FORECAST_DRIVERS.get(name)
        is_forecast = name in FORECAST_DRIVERS or name in FLAT_BASELINE_ITEMS
        items.append({
            "item_id": make_item_id(name, taken),
            "atc_code": atc_for(name),
            "display_name": name,
            "local_name_in": name,
            "spoken_variants": SPOKEN_VARIANTS.get(name, [name.lower()]),
            "unit": infer_unit(row["dosage_forms"]),
            "ven_class": classify_ven(name, row["section_no"]),
            "demand_driver": driver,
            "is_forecast_item": is_forecast,
            "flat_baseline_reason": FLAT_BASELINE_ITEMS.get(name),
            "nlem_section": int(row["section_no"]) if str(
                row["section_no"]).isdigit() else None,
            "nlem_section_name": row["section_name"],
            "level_of_care": row["level_of_care"],
            "dosage_forms": row["dosage_forms"],
        })

    _assert_curation_matches(items)
    return items


def _assert_curation_matches(items: list[dict]) -> None:
    """Fail loudly if a curated name no longer exists in the parsed NLEM.

    Without this, a rename or parser change would silently drop an item from
    the forecast set and nobody would notice until the model had no series.
    """
    names = {item["display_name"] for item in items}
    missing = sorted(
        (set(FORECAST_DRIVERS) | set(FLAT_BASELINE_ITEMS)) - names
    )
    if missing:
        raise SystemExit(
            "Curated forecast items are not present in the parsed NLEM: "
            + ", ".join(missing)
        )

    allowed_indicators = {
        "Malaria", "Childhood Diseases", "Inpatient counts",
        "Outpatient - Acute Heart Diseases", "Outpatient - Dental",
        "Outpatient - Diabetes", "Outpatient - Epilepsy",
        "Outpatient - Hypertension", "Outpatient - Mental illness",
        "Outpatient - Ophthalmic Related", "Outpatient - Stroke (Paralysis)",
    }
    bad = set(FORECAST_DRIVERS.values()) - allowed_indicators
    if bad:
        raise SystemExit(f"Unknown HMIS indicators in driver map: {sorted(bad)}")


def get_items_data() -> list[dict]:
    """Catalogue for the capture matcher."""
    return build_items()


# ---------------------------------------------------------------------------
SCHEMA = [
    bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("atc_code", "STRING"),
    bigquery.SchemaField("display_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("local_name_in", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("spoken_variants", "STRING", mode="REPEATED"),
    bigquery.SchemaField("unit", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ven_class", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("demand_driver", "STRING"),
    bigquery.SchemaField("is_forecast_item", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("flat_baseline_reason", "STRING"),
    bigquery.SchemaField("nlem_section", "INT64"),
    bigquery.SchemaField("nlem_section_name", "STRING"),
    bigquery.SchemaField("level_of_care", "STRING"),
    bigquery.SchemaField("dosage_forms", "STRING"),
]


def report(items: list[dict]) -> None:
    total = len(items)
    with_atc = sum(1 for i in items if i["atc_code"])
    forecast = [i for i in items if i["is_forecast_item"]]
    driven = [i for i in forecast if i["demand_driver"]]
    flat = [i for i in forecast if not i["demand_driver"]]

    print(f"Items:              {total}")
    print(f"  with ATC code:    {with_atc}  ({with_atc / total:.0%})")
    print(f"  without ATC code: {total - with_atc}")
    print(f"  primary-care (P): "
          f"{sum(1 for i in items if 'P' in (i['level_of_care'] or ''))}")
    print()
    print("VEN:")
    for ven in ("Vital", "Essential", "Desirable"):
        print(f"  {ven:10s} {sum(1 for i in items if i['ven_class'] == ven)}")
    print()
    print(f"is_forecast_item:   {len(forecast)} "
          f"({len(driven)} HMIS-driven, {len(flat)} flat baseline)")


def load(items: list[dict]) -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    job = client.load_table_from_json(
        items,
        TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ),
    )
    job.result()

    loaded = next(iter(client.query(
        f"SELECT COUNT(*) AS n, COUNTIF(is_forecast_item) AS f, "
        f"COUNTIF(atc_code IS NOT NULL) AS a FROM `{TABLE}`"
    ).result()))
    print(f"\nLoaded to {TABLE}: {loaded.n} rows, "
          f"{loaded.f} forecast items, {loaded.a} with ATC")
    if loaded.n != len(items):
        raise SystemExit(
            f"ROW COUNT MISMATCH: built {len(items)}, BigQuery has {loaded.n}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    built = build_items()
    report(built)
    if args.dry_run:
        print("\n[DRY RUN] Nothing written to BigQuery.")
        sys.exit(0)
    load(built)
