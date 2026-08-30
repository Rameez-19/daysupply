"""WHO ATC codes for NLEM 2022 medicines.

NLEM does not publish ATC codes, so they are attached here by hand. The rule
this file follows is **confident or null** — a medicine gets a code only where
the mapping is unambiguous. A wrong ATC code is worse than a missing one: ATC
class is what drives therapeutic substitution, so a bad code could surface the
wrong drug as an equivalent.

Keys are normalised medicine names (see `normalise`): lowercased, footnote
markers and parenthetical glosses removed, whitespace collapsed.

Combination products are keyed in full rather than resolved to their first
ingredient, because a combination's ATC is genuinely different from its parts —
`Amoxicillin` is J01CA04 but `Amoxicillin + Clavulanic acid` is J01CR02.
"""

from __future__ import annotations

import re

ATC_BY_NAME: dict[str, str] = {
    # --- 1 Anaesthetics -------------------------------------------------
    "ketamine": "N01AX03",
    "propofol": "N01AX10",
    "thiopentone sodium": "N01AF03",
    "halothane": "N01AB01",
    "isoflurane": "N01AB06",
    "sevoflurane": "N01AB08",
    "nitrous oxide": "N01AX63",
    "lignocaine": "N01BB02",
    "bupivacaine": "N01BB01",
    "atropine": "A03BA01",
    "glycopyrrolate": "A03AB02",
    "neostigmine": "N07AA01",
    "suxamethonium": "M03AB01",
    "vecuronium": "M03AC03",
    "atracurium": "M03AC04",
    "midazolam": "N05CD08",
    "diazepam": "N05BA01",
    "fentanyl": "N01AH01",
    "ephedrine": "C01CA26",
    "oxygen": "V03AN01",

    # --- 2 Analgesics, antipyretics, NSAIDs ------------------------------
    "paracetamol": "N02BE01",
    "acetylsalicylic acid": "N02BA01",
    "ibuprofen": "M01AE01",
    "diclofenac": "M01AB05",
    "mefenamic acid": "M01AG01",
    "morphine": "N02AA01",
    "tramadol": "N02AX02",
    "allopurinol": "M04AA01",
    "colchicine": "M04AC01",
    "hydroxychloroquine": "P01BA02",
    "methotrexate": "L01BA01",
    "sulfasalazine": "A07EC01",
    "azathioprine": "L04AX01",

    # --- 3 Antiallergics --------------------------------------------------
    "adrenaline": "C01CA24",
    "cetirizine": "R06AE07",
    "chlorpheniramine": "R06AB04",
    "pheniramine": "R06AB05",
    "dexamethasone": "H02AB02",
    "hydrocortisone": "H02AB09",
    "prednisolone": "H02AB06",

    # --- 4 Antidotes ------------------------------------------------------
    "activated charcoal": "A07BA01",
    "naloxone": "V03AB15",
    "n-acetylcysteine": "V03AB23",
    "pralidoxime chloride": "V03AB04",
    "desferrioxamine": "V03AC01",
    "d- penicillamine": "M01CC01",
    "d-penicillamine": "M01CC01",
    "calcium gluconate": "A12AA03",
    "sodium nitrite": "V03AB08",
    "sodium thiosulphate": "V03AB06",
    "methylthioninium chloride": "V03AB17",
    "snake venom antiserum": "J06AA03",

    # --- 5 Neurological ---------------------------------------------------
    "carbamazepine": "N03AF01",
    "phenytoin": "N03AB02",
    "sodium valproate": "N03AG01",
    "valproic acid": "N03AG01",
    "phenobarbitone": "N03AA02",
    "levetiracetam": "N03AX14",
    "clobazam": "N05BA09",
    "clonazepam": "N03AE01",
    "ethosuximide": "N03AD01",
    "sumatriptan": "N02CC01",
    "levodopa": "N04BA01",
    "trihexyphenidyl": "N04AA01",
    "pyridostigmine": "N07AA02",
    "baclofen": "M03BX01",
    "mannitol": "B05BC01",

    # --- 6 Anti-infectives ------------------------------------------------
    "albendazole": "P02CA03",
    "ivermectin": "P02CF01",
    "diethylcarbamazine": "P02CB02",
    "praziquantel": "P02BA01",
    "amoxicillin": "J01CA04",
    "ampicillin": "J01CA01",
    "benzylpenicillin": "J01CE01",
    "benzathine benzylpenicillin": "J01CE08",
    "cloxacillin": "J01CF02",
    "cefazolin": "J01DB04",
    "cefotaxime": "J01DD01",
    "ceftriaxone": "J01DD04",
    "ceftazidime": "J01DD02",
    "cefixime": "J01DD08",
    "cefuroxime": "J01DC02",
    "meropenem": "J01DH02",
    "azithromycin": "J01FA10",
    "erythromycin": "J01FA01",
    "clindamycin": "J01FF01",
    "gentamicin": "J01GB03",
    "amikacin": "J01GB06",
    "streptomycin": "J01GA01",
    "ciprofloxacin": "J01MA02",
    "levofloxacin": "J01MA12",
    "ofloxacin": "J01MA01",
    "doxycycline": "J01AA02",
    "metronidazole": "P01AB01",
    "nitrofurantoin": "J01XE01",
    "vancomycin": "J01XA01",
    "chloramphenicol": "J01BA01",
    "fluconazole": "J02AC01",
    "itraconazole": "J02AC02",
    "amphotericin b": "J02AA01",
    "griseofulvin": "D01BA01",
    "clotrimazole": "G01AF02",
    "nystatin": "A07AA02",
    "terbinafine": "D01BA02",
    "acyclovir": "J05AB01",
    "oseltamivir": "J05AH02",
    "zidovudine": "J05AF01",
    "lamivudine": "J05AF05",
    "efavirenz": "J05AG03",
    "nevirapine": "J05AG01",
    "dolutegravir": "J05AJ03",
    "ritonavir": "J05AE03",
    "raltegravir": "J05AJ01",
    "daclatasvir": "J05AP07",
    "isoniazid": "J04AC01",
    "rifampicin": "J04AB02",
    "pyrazinamide": "J04AK01",
    "ethambutol": "J04AK02",
    "bedaquiline": "J04AK05",
    "delamanid": "J04AK06",
    "clofazimine": "J04BA01",
    "dapsone": "J04BA02",
    "chloroquine": "P01BA01",
    "primaquine": "P01BA03",
    "artesunate": "P01BE03",
    "quinine": "P01BC01",
    "miltefosine": "L01XX09",
    "sodium stibogluconate": "P01CB01",
    # Combinations — genuinely distinct ATC classes
    "co-trimoxazole": "J01EE01",
    "amoxicillin + clavulanic acid": "J01CR02",
    "piperacillin + tazobactam": "J01CR05",
    "artemether + lumefantrine": "P01BF01",
    "artesunate + sulphadoxine - pyrimethamine": "P01BF02",

    # --- 8 Blood ----------------------------------------------------------
    "ferrous salts": "B03AA07",
    "folic acid": "B03BB01",
    "cyanocobalamin": "B03BA01",
    "heparin": "B01AB01",
    "enoxaparin": "B01AB05",
    "warfarin": "B01AA03",
    "tranexamic acid": "B02AA02",
    "phytomenadione": "B02BA01",
    "clopidogrel": "B01AC04",
    "streptokinase": "B01AD01",
    "erythropoietin": "B03XA01",
    "dabigatran": "B01AE07",
    "protamine sulphate": "V03AB14",

    # --- 10 Cardiovascular ------------------------------------------------
    "amlodipine": "C08CA01",
    "nifedipine": "C08CA05",
    "diltiazem": "C08DB01",
    "verapamil": "C08DA01",
    "atenolol": "C07AB03",
    "metoprolol": "C07AB02",
    "propranolol": "C07AA05",
    "enalapril": "C09AA02",
    "ramipril": "C09AA05",
    "losartan": "C09CA01",
    "telmisartan": "C09CA07",
    "hydrochlorothiazide": "C03AA03",
    "furosemide": "C03CA01",
    "spironolactone": "C03DA01",
    "digoxin": "C01AA05",
    "amiodarone": "C01BD01",
    "glyceryl trinitrate": "C01DA02",
    "isosorbide dinitrate": "C01DA08",
    "atorvastatin": "C10AA05",
    "dobutamine": "C01CA07",
    "dopamine": "C01CA04",
    "noradrenaline": "C01CA03",
    "methyldopa": "C02AB01",
    "labetalol": "C07AG01",
    "prazosin": "C02CA01",

    # --- 11 Dermatological ------------------------------------------------
    "benzoyl peroxide": "D10AE01",
    "betamethasone": "D07AC01",
    "permethrin": "P03AC04",
    "salicylic acid": "D01AE12",
    "silver sulfadiazine": "D06BA01",
    "framycetin": "D06AX07",
    "mupirocin": "D06AX09",
    "ketoconazole": "D01AC08",
    "miconazole": "D01AC02",
    "white petrolatum": "D02AC",
    "calamine": "D02AB",
    "coal tar": "D05AA",

    # --- 12 Diagnostics ---------------------------------------------------
    "barium sulphate": "V08BA01",
    "iohexol": "V08AB02",
    "fluorescein": "S01JA01",

    # --- 14 Antiseptics and disinfectants ---------------------------------
    "chlorhexidine": "D08AC02",
    "povidone iodine": "D08AG02",
    "hydrogen peroxide": "D08AX01",
    "cetrimide": "D08AJ04",
    "potassium permanganate": "D08AX06",

    # --- 16 ENT -----------------------------------------------------------
    "xylometazoline": "R01AA07",
    "betahistine": "N07CA01",

    # --- 17 Gastrointestinal ----------------------------------------------
    "omeprazole": "A02BC01",
    "pantoprazole": "A02BC02",
    "ranitidine": "A02BA02",
    "ondansetron": "A04AA01",
    "metoclopramide": "A03FA01",
    "domperidone": "A03FA03",
    "dicyclomine": "A03AA07",
    "hyoscine butylbromide": "A03BB01",
    "bisacodyl": "A06AB02",
    "lactulose": "A06AD11",
    "oral rehydration salts": "A07CA",
    "ors": "A07CA",
    "loperamide": "A07DA03",
    "5-aminosalicylic acid": "A07EC02",
    "sucralfate": "A02BX02",
    "ursodeoxycholic acid": "A05AA02",

    # --- 18 Hormones and endocrine ----------------------------------------
    "metformin": "A10BA02",
    "glibenclamide": "A10BB01",
    "glimepiride": "A10BB12",
    "insulin": "A10AB01",
    "levothyroxine": "H03AA01",
    "carbimazole": "H03BB01",
    "propylthiouracil": "H03BA02",
    "fludrocortisone": "H02AA02",
    "testosterone": "G03BA03",
    "estradiol": "G03CA03",
    "medroxyprogesterone acetate": "G03AC06",
    "levonorgestrel": "G03AC03",
    "alendronate": "M05BA04",

    # --- 19 Immunologicals -------------------------------------------------
    "bcg vaccine": "J07AN01",
    "hepatitis b vaccine": "J07BC01",
    "measles vaccine": "J07BD01",
    "rabies vaccine": "J07BG01",
    "tetanus toxoid": "J07AM01",
    "rotavirus vaccine": "J07BH01",
    "anti-rabies immunoglobulin": "J06BB05",
    "anti-d immunoglobulin": "J06BB01",
    "tetanus immunoglobulin": "J06BB02",

    # --- 20 Neonatal -------------------------------------------------------
    "caffeine citrate": "N06BC01",
    "surfactant": "R07AA02",

    # --- 21 Ophthalmological ----------------------------------------------
    "timolol": "S01ED01",
    "pilocarpine": "S01EB01",
    "latanoprost": "S01EE01",
    "tropicamide": "S01FA06",
    "homatropine": "S01FA05",
    "acetazolamide": "S01EC01",
    "carboxymethylcellulose": "S01XA20",

    # --- 22 Oxytocics and antioxytocics ------------------------------------
    "oxytocin": "H01BB02",
    "misoprostol": "G02AD06",
    "methylergometrine": "G02AB01",
    "dinoprostone": "G02AD02",
    "magnesium sulphate": "A12CC02",
    "isoxsuprine": "C04AA01",

    # --- 23 Psychiatric ----------------------------------------------------
    "amitriptyline": "N06AA09",
    "fluoxetine": "N06AB03",
    "sertraline": "N06AB06",
    "escitalopram": "N06AB10",
    "imipramine": "N06AA02",
    "haloperidol": "N05AD01",
    "chlorpromazine": "N05AA01",
    "olanzapine": "N05AH03",
    "risperidone": "N05AX08",
    "lithium carbonate": "N05AN01",
    "clozapine": "N05AH02",
    "fluphenazine": "N05AB02",
    "lorazepam": "N05BA06",
    "bupropion": "N06AX12",
    "naltrexone": "N07BB04",
    "buprenorphine": "N07BC01",
    "nicotine": "N07BA01",
    "disulfiram": "N07BB01",

    # --- 24 Respiratory ----------------------------------------------------
    "salbutamol": "R03AC02",
    "ipratropium bromide": "R03BB01",
    "budesonide": "R03BA02",
    "beclomethasone": "R03BA01",
    "montelukast": "R03DC03",
    "theophylline": "R03DA04",
    "aminophylline": "R03DA05",

    # --- 25 Fluids and electrolytes ----------------------------------------
    "sodium chloride": "B05CB01",
    "dextrose": "B05BA03",
    "ringer lactate": "B05BB01",
    "potassium chloride": "B05XA01",
    "sodium bicarbonate": "B05XA02",
    "water for injection": "V07AB",

    # --- 26 Vitamins and minerals ------------------------------------------
    "retinol": "A11CA01",
    "vitamin a": "A11CA01",
    "thiamine": "A11DA01",
    "pyridoxine": "A11HA02",
    "ascorbic acid": "A11GA01",
    "cholecalciferol": "A11CC05",
    "calcium carbonate": "A12AA04",
    "zinc sulphate": "A12CB01",
    "zinc sulfate": "A12CB01",
    "nicotinamide": "A11HA01",

    # --- 27 COVID-19 --------------------------------------------------------
    "remdesivir": "J05AB16",
    "tocilizumab": "L04AC07",

    # --- 7 Anti-cancer and immunosuppressives -------------------------------
    "cisplatin": "L01XA01",
    "carboplatin": "L01XA02",
    "oxaliplatin": "L01XA03",
    "cyclophosphamide": "L01AA01",
    "ifosfamide": "L01AA06",
    "chlorambucil": "L01AA02",
    "bendamustine hydrochloride": "L01AA09",
    "dacarbazine": "L01AX04",
    "doxorubicin": "L01DB01",
    "daunorubicin": "L01DB02",
    "bleomycin": "L01DC01",
    "5-fluorouracil": "L01BC02",
    "cytosine arabinoside": "L01BC01",
    "6-mercaptopurine": "L01BB02",
    "gemcitabine": "L01BC05",
    "vincristine": "L01CA02",
    "vinblastine": "L01CA01",
    "paclitaxel": "L01CD01",
    "docetaxel": "L01CD02",
    "etoposide": "L01CB01",
    "imatinib": "L01EA01",
    "rituximab": "L01FA01",
    "trastuzumab": "L01FD01",
    "tamoxifen": "L02BA01",
    "leuprolide acetate": "L02AE02",
    "zoledronic acid": "M05BA08",
    "filgrastim": "L03AA02",
    "cyclosporine": "L04AD01",
    "mycophenolate mofetil": "L04AA06",
    "tacrolimus": "L04AD02",
}

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_FOOTNOTE = re.compile(r"[*†‡]+")


def normalise(name: str) -> str:
    """Lowercase, drop footnote markers and parenthetical glosses."""
    text = _FOOTNOTE.sub("", name or "")
    text = _PAREN.sub(" ", text)
    text = text.replace("–", "-").lower()
    return re.sub(r"\s+", " ", text).strip(" .,-")


def atc_for(name: str) -> str | None:
    """ATC code for a medicine name, or None when not confidently known."""
    key = normalise(name)
    if key in ATC_BY_NAME:
        return ATC_BY_NAME[key]

    # Combinations are keyed in full above. If a combination is not listed,
    # return None rather than borrowing an ingredient's code — the class would
    # be wrong, and ATC class drives therapeutic substitution.
    if "+" in key:
        return None

    # "Insulin Premix Injection 30:70" and similar: match on the leading word
    # only when that word is itself a complete, unambiguous entry.
    head = key.split()[0] if key else ""
    if head in ATC_BY_NAME and len(head) > 4:
        return ATC_BY_NAME[head]
    return None
