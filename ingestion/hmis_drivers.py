"""Which HMIS data items make up each demand driver.

**Drivers are defined by item code, never by matching words in the label.**
That distinction is not pedantic — it is the whole reason this file exists.

The previous parser mapped any label containing "malaria" to a single `Malaria`
driver. In Maharashtra that summed:

    11.1.1.a  Total Blood Smears Examined for Malaria     14,525,963
    11.1.2.a  RDT conducted for Malaria                    1,087,554
    11.1.1.b/c, 11.1.2.b/c  confirmed positives               24,831
    10.10, 14.4.1, 16.8.1/2  childhood, inpatient, deaths     12,220

Confirmed cases were **0.16%** of the total, so antimalarial demand was being
forecast from how many blood smears a district collected — testing effort, not
disease. Substring matching cannot tell "tests conducted" from "tests positive";
an explicit code list can.

Each driver below names its HMIS codes and the clinical reason it drives the
medicines assigned to it. The reasoning belongs here, next to the mapping,
because a mapping table alone is not defensible under questioning.
"""

from __future__ import annotations

# How much of a district's activity for each driver actually flows through a
# PHC. The generator divides a district total by the number of PHCs in it, and
# without this it would implicitly assume PHCs handle everything — but
# sub-centres do much of antenatal care, and district hospitals take most
# admissions. These are documented assumptions, not measurements; they live
# here so every one of them is inspectable in a single place.
PHC_SHARE: dict[str, float] = {
    "Malaria - confirmed cases": 0.50,
    "Outpatient - Hypertension": 0.30,
    "Outpatient - Diabetes": 0.30,
    "Outpatient - Epilepsy": 0.30,
    "Outpatient - Mental illness": 0.25,
    "Outpatient - Ophthalmic Related": 0.25,
    "Outpatient - Dental": 0.30,
    "Cardiac - outpatient and emergency": 0.25,
    "Stroke - outpatient and emergency": 0.25,
    "Childhood diarrhoea": 0.45,
    "Childhood pneumonia and respiratory infection": 0.45,
    "Vitamin A doses administered": 0.40,
    "Albendazole doses administered": 0.40,
    "Asthma and COPD": 0.35,
    "Inpatient admissions - total": 0.15,
    "Inpatient admissions - infectious": 0.15,
    "Outpatient attendance - allopathic": 0.35,
    "IFA tablets issued to pregnant women": 0.30,
    "Institutional deliveries": 0.25,
    "Eclampsia cases managed": 0.15,
    "Antenatal registrations": 0.30,
}

# driver name -> (HMIS item codes, what it counts, why it drives demand)
DRIVERS: dict[str, tuple[list[str], str, str]] = {

    # --- Vector-borne -----------------------------------------------------
    "Malaria - confirmed cases": (
        ["11.1.1.b", "11.1.1.c", "11.1.2.b", "11.1.2.c"],
        "Microscopy and RDT positives, P. vivax and P. falciparum",
        "Antimalarial consumption follows confirmed cases. Blood smears "
        "examined (11.1.1.a) is testing effort driven by surveillance "
        "campaigns and is deliberately excluded.",
    ),

    # --- Chronic outpatient ------------------------------------------------
    "Outpatient - Hypertension": (
        ["14.1.2"],
        "Hypertension outpatient attendances",
        "Antihypertensives are dispensed per outpatient review, typically a "
        "month's supply at a time.",
    ),
    "Outpatient - Diabetes": (
        ["14.1.1"],
        "Diabetes outpatient attendances",
        "Oral hypoglycaemics and insulin are dispensed per review.",
    ),
    "Outpatient - Epilepsy": (
        ["14.1.6"],
        "Epilepsy outpatient attendances",
        "Anticonvulsants are dispensed per review; adherence is continuous.",
    ),
    "Outpatient - Mental illness": (
        ["14.1.5"],
        "Mental illness outpatient attendances",
        "Psychotropics are dispensed per review.",
    ),
    "Outpatient - Ophthalmic Related": (
        ["14.1.7"],
        "Ophthalmic outpatient attendances",
        "The narrowest available proxy. HMIS publishes no glaucoma-specific "
        "indicator, which is what Timolol actually treats.",
    ),
    "Outpatient - Dental": (
        ["14.1.8"],
        "Dental outpatient attendances",
        "The only dental indicator HMIS publishes.",
    ),
    "Cardiac - outpatient and emergency": (
        ["14.1.4", "14.6.5"],
        "Acute heart disease outpatients plus acute cardiac emergencies",
        "Antiplatelets, nitrates and statins are started in both settings, so "
        "both are counted.",
    ),
    "Stroke - outpatient and emergency": (
        ["14.1.3", "14.6.7"],
        "Stroke outpatients plus cerebrovascular emergencies",
        "Secondary-prevention antiplatelets are started after either "
        "presentation.",
    ),

    # --- Paediatric --------------------------------------------------------
    "Childhood diarrhoea": (
        ["10.11", "10.12"],
        "Childhood diarrhoea, outpatient and inpatient",
        "Diarrhoea is the sole indication for ORS and for zinc "
        "supplementation under the WHO/MoHFW protocol.",
    ),
    "Childhood pneumonia and respiratory infection": (
        ["10.1", "10.13"],
        "Childhood pneumonia plus admissions for upper respiratory infection",
        "Amoxicillin is WHO first-line for childhood pneumonia.",
    ),
    "Vitamin A doses administered": (
        ["9.8.1", "9.8.2", "9.8.3"],
        "Vitamin A doses 1, 5 and 9 given at immunisation contacts",
        "Counts the doses actually administered. Vitamin A is a scheduled "
        "supplement, so its demand follows the immunisation calendar and not "
        "disease incidence at all.",
    ),
    "Albendazole doses administered": (
        ["9.10"],
        "Children aged 12-59 months given Albendazole",
        "Counts the doses actually administered. Deworming is a campaign; it "
        "is not driven by presenting illness.",
    ),
    "Asthma and COPD": (
        ["10.2", "14.4.4"],
        "Childhood asthma plus admissions for asthma, COPD and respiratory "
        "infection",
        "Bronchodilator demand follows obstructive airway presentations "
        "across both children and adults.",
    ),

    # --- Inpatient ---------------------------------------------------------
    "Inpatient admissions - total": (
        ["14.3.1.a", "14.3.1.b", "14.3.2.a", "14.3.2.b"],
        "All admissions: male and female, children and adults",
        "Intravenous fluid use scales with total bed occupancy regardless of "
        "diagnosis.",
    ),
    "Inpatient admissions - infectious": (
        ["14.4.1", "14.4.2", "14.4.3", "14.4.5", "14.4.6", "14.4.7", "14.4.8"],
        "Admissions for malaria, dengue, typhoid, TB, PUO, diarrhoea with "
        "dehydration and hepatitis",
        "Empirical intravenous antibiotics go to infectious admissions, not "
        "to the whole ward.",
    ),

    # --- General outpatient load -------------------------------------------
    "Outpatient attendance - allopathic": (
        ["14.2.1"],
        "Total allopathic outpatient attendance",
        "General analgesics and antipyretics track total attendance rather "
        "than any one diagnosis. This indicator exists and was simply not "
        "parsed before, which is why these items previously had no driver.",
    ),

    # --- Maternal ----------------------------------------------------------
    "IFA tablets issued to pregnant women": (
        ["1.2.4"],
        "Pregnant women given the full 180-tablet IFA course",
        "Counts issuance of the drug itself, so it is a direct measure of "
        "consumption rather than a proxy for it.",
    ),
    "Institutional deliveries": (
        ["2.2"],
        "Institutional deliveries including caesareans",
        "Oxytocin is given routinely in active management of the third stage "
        "of labour, so demand is one dose per delivery.",
    ),
    "Eclampsia cases managed": (
        ["1.3.2"],
        "Eclampsia cases managed during delivery",
        "Magnesium sulphate treats eclampsia specifically, not delivery "
        "generally. Institutional deliveries would overstate demand roughly "
        "300-fold.",
    ),
    "Antenatal registrations": (
        ["1.1"],
        "Pregnant women registered for antenatal care",
        "Kept as a general maternal-activity series for the pattern "
        "exchange; no medicine is assigned to it directly.",
    ),
}

# Codes that must never be summed into a case-count driver, with the reason.
# Recorded so the exclusion is a decision on the record, not an omission.
DELIBERATE_EXCLUSIONS: dict[str, str] = {
    "11.1.1.a": "Blood smears examined — testing effort, not cases",
    "11.1.2.a": "RDTs conducted — testing effort, not cases",
    "14.9.1": "Inpatient deaths (male) — an outcome, not an admission",
    "14.9.2": "Inpatient deaths (female) — an outcome, not an admission",
    "16.8.1": "Deaths from P. vivax malaria — an outcome, not a case",
    "16.8.2": "Deaths from P. falciparum malaria — an outcome, not a case",
    "14.10": "In-patient head count at midnight — bed-days, which would "
             "double-count against admissions",
    "14.2.2": "AYUSH outpatient attendance — not served by the allopathic "
              "essential-medicines supply chain",
}

# Every code any driver depends on.
ALL_CODES: set[str] = {
    code for codes, _, _ in DRIVERS.values() for code in codes
}


def driver_for_code(code: str) -> str | None:
    """Which driver a given HMIS item code contributes to, if any."""
    for name, (codes, _, _) in DRIVERS.items():
        if code in codes:
            return name
    return None


def phc_share(driver: str) -> float:
    """Share of a district's activity for this driver handled by PHCs."""
    return PHC_SHARE.get(driver, 0.3)
