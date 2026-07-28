import random
import re
from dataclasses import dataclass

#: The only power types the simulator can model. An appliance record may state
#: one explicitly as ``power_type``; anything else is a load-time error.
POWER_TYPES = ('solar', 'mains')


def device_label(device_dict):
    '''
    Build a human-readable label for a catalog record, for use in error
    messages. Works for both appliance (A*) and logger (L*) records.
    '''
    pqs = device_dict.get('APQS') or device_dict.get('LPQS') or '?'
    manufacturer = device_dict.get('AMFR') or device_dict.get('LMFR') or '?'
    model = device_dict.get('AMOD') or device_dict.get('LMOD') or '?'
    return f"{pqs} ({manufacturer} {model})"


def device_manufacturer(device_dict):
    '''
    Return a catalog record's manufacturer, whichever key style it uses --
    'AMFR' on an appliance record, 'LMFR' on a logger one.

    Resolved per record rather than once per list, so a list that mixes the two
    (or that happens to start with an odd row) still groups correctly.
    '''
    manufacturer = device_dict.get('AMFR') or device_dict.get('LMFR')
    if manufacturer is None:
        raise ValueError(
            f"Catalog record {device_label(device_dict)} has no manufacturer: "
            f"expected 'AMFR' or 'LMFR'"
        )
    return manufacturer


def validate_power_type(power_type, label):
    '''
    Normalize and validate an explicit power_type value.

    Returns None when no value was given (the caller then falls back to
    sniffing the free-text type string). Otherwise returns the value
    lower-cased, or raises ValueError naming the offending appliance -- an
    unrecognized power type must never fall through to a default, because the
    power type selects the entire physical model of the appliance.
    '''
    if power_type is None:
        return None
    normalized = power_type.strip().lower() if isinstance(power_type, str) else power_type
    if normalized not in POWER_TYPES:
        raise ValueError(
            f"Invalid power_type {power_type!r} for appliance {label}: "
            f"expected one of {', '.join(repr(p) for p in POWER_TYPES)}"
        )
    return normalized


@dataclass
class Device:
    manufacturer: str
    model: str
    pqs_code: str
    type: str
    #: Explicit power type ('solar' or 'mains'). None means the appliance
    #: record did not state one, and the power type is inferred from `type`.
    power_type: str = None

    @classmethod
    def from_dict(cls, device_dict):
        '''
        Create a Device instance from a dictionary. Automatically resolves
        the correct keys for manufacturer, model, and pqs_code based on the
        key style of the record: appliance (A*) or logger (L*).
        '''
        power_type = validate_power_type(
            device_dict.get('power_type'), device_label(device_dict)
        )
        if 'AMFR' in device_dict:
            return cls(
                manufacturer=device_dict['AMFR'],
                model=device_dict['AMOD'],
                pqs_code=device_dict['APQS'],
                type=device_dict['type'],
                power_type=power_type
            )
        elif 'LMFR' in device_dict:
            return cls(
                manufacturer=device_dict['LMFR'],
                model=device_dict['LMOD'],
                pqs_code=device_dict['LPQS'],
                type=device_dict['type'],
                power_type=power_type
            )
        else:
            raise ValueError("Unknown device type: Unable to resolve keys.")

#: The full WHO PQS E003 prequalified appliance catalogue. Not the packaged
#: default -- it ships as the named builtin `Catalogs.builtin('pqs-e003-full')`
#: for anyone who wants to simulate the whole prequalified range.
pqs_e003_fridges = [
    {"APQS": "E003/002", "type": "Vaccine/Waterpacks freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBD 116", "power_type": "mains"},
    {"APQS": "E003/003", "type": "Vaccine/Waterpacks freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBD 286", "power_type": "mains"},
    {"APQS": "E003/007", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "MK 304", "power_type": "mains"},
    {"APQS": "E003/011", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "MK 204", "power_type": "mains"},
    {"APQS": "E003/022", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "MK 144", "power_type": "mains"},
    {"APQS": "E003/024", "type": "Vaccine/Waterpacks freezer", "AMFR": "Vestfrost Solutions", "AMOD": "MF 114", "power_type": "mains"},
    {"APQS": "E003/025", "type": "Vaccine/Waterpacks freezer", "AMFR": "Vestfrost Solutions", "AMOD": "MF 214", "power_type": "mains"},
    {"APQS": "E003/023", "type": "Vaccine/Waterpacks freezer", "AMFR": "Vestfrost Solutions", "AMOD": "MF 314", "power_type": "mains"},
    {"APQS": "E003/035", "type": "Solar direct drive refrigerator/freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 2000 SDD", "power_type": "solar"},
    {"APQS": "E003/030", "type": "Solar direct drive refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 3000 SDD", "power_type": "solar"},
    {"APQS": "E003/048", "type": "Solar Direct Drive Combined Refrigerator/Freezer", "AMFR": "Dulas Ltd", "AMOD": "VC150SDD", "power_type": "solar"},
    {"APQS": "E003/037", "type": "Solar direct drive refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF 100 DC (SureChill ®)", "power_type": "solar"},
    {"APQS": "E003/106", "type": "Solar direct drive refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 054A SDD", "power_type": "solar"},
    {"APQS": "E003/043", "type": "Solar direct drive refrigerator/freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 2043 SDD", "power_type": "solar"},
    {"APQS": "E003/042", "type": "Solar direct drive refrigerator/freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 40 SDD", "power_type": "solar"},
    {"APQS": "E003/044", "type": "Icelined refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF 150 AC (SureChill ®)", "power_type": "mains"},
    {"APQS": "E003/045", "type": "Solar direct drive refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 3043 SDD", "power_type": "solar"},
    {"APQS": "E003/049", "type": "Solar Direct Drive Refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 50DC SDD", "power_type": "solar"},
    {"APQS": "E003/061", "type": "Vaccine/Waterpack freezer", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "DW-25W300", "power_type": "mains"},
    {"APQS": "E003/050", "type": "Solar Direct Drive Refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 100 DC (SureChill®)", "power_type": "solar"},
    {"APQS": "E003/051", "type": "Ice-lined refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF30 AC (SureChill ®)", "power_type": "mains"},
    {"APQS": "E003/052", "type": "Solar direct drive refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF 150 DC (SureChill ®)", "power_type": "solar"},
    {"APQS": "E003/107", "type": "Solar direct drive refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 094A SDD", "power_type": "solar"},
    {"APQS": "E003/108", "type": "Solar direct drive refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 154A SDD Greenline", "power_type": "solar"},
    {"APQS": "E003/057", "type": "Solar Direct Drive Combined Refrigerator/Freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTCD-160-SDD", "power_type": "solar"},
    {"APQS": "E003/055", "type": "Solar direct drive refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF 30DC SDD (SureChill ®)", "power_type": "solar"},
    {"APQS": "E003/058", "type": "Solar Direct Drive vaccine refrigerator", "AMFR": "Dulas Ltd", "AMOD": "Dulas VC110SDD", "power_type": "solar"},
    {"APQS": "E003/059", "type": "Solar Direct Drive vaccine refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC88SDD", "power_type": "solar"},
    {"APQS": "E003/040", "type": "Solar Direct Drive Refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC200SDD", "power_type": "solar"},
    {"APQS": "E003/060", "type": "Vaccine/waterpack freezer", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "DW-25W147", "power_type": "mains"},
    {"APQS": "E003/068", "type": "Solar Direct Drive refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 40R SDD", "power_type": "solar"},
    {"APQS": "E003/109", "type": "Mains-powered refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 204A", "power_type": "mains"},
    {"APQS": "E003/066", "type": "Icelined refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 4000 AC", "power_type": "mains"},
    {"APQS": "E003/073", "type": "Solar Direct Drive Waterpacks Freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TFW 40 SDD", "power_type": "solar"},
    {"APQS": "E003/110", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 304A AC", "power_type": "mains"},
    {"APQS": "E003/111", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 354A AC", "power_type": "mains"},
    {"APQS": "E003/112", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 404A AC", "power_type": "mains"},
    {"APQS": "E003/069", "type": "Solar direct drive refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 024 SDD", "power_type": "solar"},
    {"APQS": "E003/070", "type": "Combined icelined refrigerator/waterpacks freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 064 RF AC", "power_type": "mains"},
    {"APQS": "E003/067", "type": "Solar direct drive refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 15R SDD", "power_type": "solar"},
    {"APQS": "E003/071", "type": "Waterpacks freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TFW 3000 AC", "power_type": "mains"},
    {"APQS": "E003/072", "type": "Icelined refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC225ILR", "power_type": "mains"},
    {"APQS": "E003/075", "type": "Solar direct drive refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTC 40 SDD", "power_type": "solar"},
    {"APQS": "E003/076", "type": "Solar direct drive refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTC 110 SDD", "power_type": "solar"},
    {"APQS": "E003/074", "type": "Solar direct drive refrigerator/freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTCD 90 SDD", "power_type": "solar"},
    {"APQS": "E003/079", "type": "Icelined refrigerator", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "CFD-50", "power_type": "mains"},
    {"APQS": "E003/077", "type": "Solar Direct Drive Refrigerator and Freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW15 SDD", "power_type": "solar"},
    {"APQS": "E003/078", "type": "Solar Direct Drive refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC50SDD", "power_type": "solar"},
    {"APQS": "E003/080", "type": "Ice-lined refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 51 LITE AC", "power_type": "mains"},
    {"APQS": "E003/081", "type": "Ice-lined refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 75 Lite", "power_type": "mains"},
    {"APQS": "E003/082", "type": "Ice-lined refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 99 Lite", "power_type": "mains"},
    {"APQS": "E003/083", "type": "Ice-lined refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 225 AC", "power_type": "mains"},
    {"APQS": "E003/084", "type": "Solar Direct Drive refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC60SDD-1", "power_type": "solar"},
    {"APQS": "E003/085", "type": "Solar Direct Drive Refrigerator", "AMFR": "Dulas Ltd", "AMOD": "VC30SDD", "power_type": "solar"},
    {"APQS": "E003/086", "type": "Solar Direct Drive Waterpacks Freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTD-40", "power_type": "solar"},
    {"APQS": "E003/087", "type": "Ice-lined Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBC-260", "power_type": "mains"},
    {"APQS": "E003/088", "type": "Ice-lined Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBC-150", "power_type": "mains"},
    {"APQS": "E003/089", "type": "Ice-lined Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBC-80", "power_type": "mains"},
    {"APQS": "E003/090", "type": "Solar Direct Drive Refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "Ultra 16 SDD", "power_type": "solar"},
    {"APQS": "E003/091", "type": "Solar Direct Drive Refrigerator and Freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 026 RF SDD", "power_type": "solar"},
    {"APQS": "E003/092", "type": "Solar Direct Drive Refrigerator and Freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 056 RF SDD", "power_type": "solar"},
    {"APQS": "E003/093", "type": "Solar Direct Drive Refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 4000 SDD", "power_type": "solar"},
    {"APQS": "E003/095", "type": "Solar Direct Drive Refrigerator and Freezer", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 55 FF DC", "power_type": "solar"},
    {"APQS": "E003/113", "type": "Ice-lined Refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 504A AC", "power_type": "mains"},
    {"APQS": "E003/096", "type": "Ice-lined Refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF80AC (SureChill®)", "power_type": "mains"},
    {"APQS": "E003/097", "type": "Combined Refrigerator and waterpack freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBCD-90", "power_type": "mains"},
    {"APQS": "E003/098", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "CFD-50 SDD", "power_type": "solar"},
    {"APQS": "E003/099", "type": "Solar Direct Drive Waterpacks Freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VFS 048 SDD", "power_type": "solar"},
    {"APQS": "E003/100", "type": "Ice-lined Refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 40R AC", "power_type": "mains"},
    {"APQS": "E003/101", "type": "Ice-lined Refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 80 AC", "power_type": "mains"},
    {"APQS": "E003/102", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTC-112", "power_type": "solar"},
    {"APQS": "E003/103", "type": "Combined Refrigerator and Waterpack Freezer", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GVR 55 FF AC", "power_type": "mains"},
    {"APQS": "E003/114", "type": "Ice-lined Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBC-120", "power_type": "mains"},
    {"APQS": "E003/115", "type": "Ice-lined Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBC-240", "power_type": "mains"},
    {"APQS": "E003/116", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTC-120-SDD", "power_type": "solar"},
    {"APQS": "E003/117", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTC-240-SDD", "power_type": "solar"},
    {"APQS": "E003/118", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "ARKTEK YBC-10 SDD", "power_type": "solar"},
    {"APQS": "E003/119", "type": "Solar Direct Drive Refrigerator/Water pack freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 076 RF SDD", "power_type": "solar"},
    {"APQS": "E003/120", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 174A AC", "power_type": "mains"},
    {"APQS": "E003/121", "type": "Solar Direct Drive Refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW80-SDD", "power_type": "solar"},
    {"APQS": "E003/122", "type": "Icelined refrigerator", "AMFR": "Coolfinity Medical B.V.", "AMOD": "IceVolt 300P", "power_type": "mains"},
    {"APQS": "E003/123", "type": "Combined Icelined Refrigerator & Freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW120AC", "power_type": "mains"},
    {"APQS": "E003/124", "type": "Vaccine Refrigerator / Ice-pack Freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW120SDD", "power_type": "solar"},
    {"APQS": "E003/125", "type": "Vaccine Freezer - Ultralow Temperature Storage", "AMFR": "B Medical Systems Sarl", "AMOD": "U201", "power_type": "mains"},
    {"APQS": "E003/126", "type": "Vaccine/Waterpacks Freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBD-86", "power_type": "mains"},
    {"APQS": "E003/127", "type": "Vaccine/Waterpack Freezer", "AMFR": "Western Refrigeration Private Limited", "AMOD": "VFW140H-HC", "power_type": "mains"},
    {"APQS": "E003/128", "type": "Vaccine/Waterpacks Freezer", "AMFR": "Western Refrigeration Private Limited", "AMOD": "VFW310H-HC", "power_type": "mains"},
    {"APQS": "E003/129", "type": "Solar Direct Drive Refrigerator & Freezer", "AMFR": "Qingdao Aucma Global Medical Co.,Ltd.", "AMOD": "TCD-100", "power_type": "solar"},
    {"APQS": "E003/130", "type": "Vaccine/waterpaks freezer", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GMF 200 ECO lite", "power_type": "mains"},
    {"APQS": "E003/132", "type": "Solar Direct Drive Refrigerator/Water pack freezer", "AMFR": "Vestfrost Solutions", "AMOD": "VLS 096A RF SDD", "power_type": "solar"},
    {"APQS": "E003/131", "type": "Combined icelined refrigerator/waterpaks freezer", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HBD265", "power_type": "mains"},
    {"APQS": "E003/133", "type": "Icelined refrigerator", "AMFR": "Western Refrigeration Private Limited", "AMOD": "I425H120", "power_type": "mains"},
    {"APQS": "E003/134", "type": "Transportable vaccine storage device - Lightweight", "AMFR": "BlackFrog Technologies Private Limited", "AMOD": "Emvolio Plus", "power_type": "mains"},
    {"APQS": "E003/135", "type": "Solar Direct Drive Refrigerator", "AMFR": "Qingdao Haier Biomedical Co., Ltd", "AMOD": "HTCD-160B", "power_type": "solar"},
    {"APQS": "E003/136", "type": "IceLined Refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GHR 200 AC", "power_type": "mains"},
    {"APQS": "E003/137", "type": "Icelined Refrigerator", "AMFR": "Godrej & Boyce MFG. Co. Ltd.", "AMOD": "GHR 90 AC", "power_type": "mains"}
]

#: The full WHO PQS E006 prequalified remote temperature monitoring device
#: catalogue. Ships as part of `Catalogs.builtin('pqs-e003-full')`.
pqs_e006_rtmds = [
    {"LPQS":"E006/019", "type": "Remote Temperature Monitoring Device","LMFR":"Berlinger & Co. AG", "LMOD":"SmartLine"},
    {"LPQS":"E006/087", "type": "Remote Temperature Monitoring Device","LMFR":"Berlinger & Co. AG", "LMOD":"SmartMonitor SITE L"},
    {"LPQS":"E006/036", "type": "Remote Temperature Monitoring Device","LMFR":"Beyond Wireless Technology Ltd", "LMOD":"ICE3 - Model BC141"},
    {"LPQS":"E006/037", "type": "Remote Temperature Monitoring Device","LMFR":"Beyond Wireless Technology Ltd", "LMOD":"Ice3-Extra-BC440"},
    {"LPQS":"E006/039", "type": "Remote Temperature Monitoring Device","LMFR":"Nexleaf Analytics", "LMOD":"ColdTrace 5"},
    {"LPQS":"E006/091", "type": "Remote Temperature Monitoring System","LMFR":"Nexleaf Analytics", "LMOD":"CTX"},
    {"LPQS":"E006/048", "type": "Remote Temperature Monitoring Device","LMFR":"Blulog Sp. z o.o", "LMOD":"Blulog"},
    {"LPQS":"E006/055", "type": "Remote Temperature Monitoring Device","LMFR":"Zero Appliances Ltd", "LMOD":"Stat-Send"},
    {"LPQS":"E006/061", "type": "Remote Temperature Monitoring Device","LMFR":"IKHAYA Automation systems", "LMOD":"VM1000"},
    {"LPQS":"E006/060", "type": "Remote Temperature Monitoring Device","LMFR":"Qingdao Haier Biomedical Co., Ltd", "LMOD":"Haier U-Cool"},
    {"LPQS":"E006/075", "type": "Remote Temperature Monitoring Device","LMFR":"Qingdao Haier Biomedical Co., Ltd", "LMOD":"U-COOL-LORA"},
    {"LPQS":"E006/078", "type": "Remote Temperature Monitoring Device","LMFR":"Qingdao Haier Biomedical Co., Ltd", "LMOD":"U-COOL Pro"},
    {"LPQS":"E006/080", "type": "Remote Temperature Monitoring Device","LMFR":"Parsyl Inc.", "LMOD":"Parsyl Trek Pro & Gateway"}
]

#: THE PACKAGED DEFAULT APPLIANCE CATALOG: a small sample, not an endorsement.
#: Six appliances covering the archetypes the physics actually distinguishes --
#: mains ice-lined, mains freezer, solar direct drive refrigerator, solar direct
#: drive combined refrigerator/freezer -- so a bare `MonitoringDeviceConfig()`
#: exercises every power and thermal model rather than one of them ninety-six
#: times. Bring your own catalog with `Catalogs.from_dir()` or
#: `CCESIM_CATALOG_DIR`; for the whole prequalified range use
#: `Catalogs.builtin('pqs-e003-full')`.
#:
#: Every row states `power_type` explicitly. E003/124 is here on purpose: it is
#: a solar direct drive whose type string says only 'Vaccine Refrigerator /
#: Ice-pack Freezer', so it is the row that shows why the free-text sniff is a
#: fallback and not the answer.
fridges = [
    {"APQS": "E003/007", "type": "Icelined refrigerator", "AMFR": "Vestfrost Solutions", "AMOD": "MK 304", "power_type": "mains"},
    {"APQS": "E003/044", "type": "Icelined refrigerator", "AMFR": "Zero Appliances Ltd", "AMOD": "ZLF 150 AC (SureChill ®)", "power_type": "mains"},
    {"APQS": "E003/024", "type": "Vaccine/Waterpacks freezer", "AMFR": "Vestfrost Solutions", "AMOD": "MF 114", "power_type": "mains"},
    {"APQS": "E003/030", "type": "Solar direct drive refrigerator", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW 3000 SDD", "power_type": "solar"},
    {"APQS": "E003/048", "type": "Solar Direct Drive Combined Refrigerator/Freezer", "AMFR": "Dulas Ltd", "AMOD": "VC150SDD", "power_type": "solar"},
    {"APQS": "E003/124", "type": "Vaccine Refrigerator / Ice-pack Freezer", "AMFR": "B Medical Systems Sarl", "AMOD": "TCW120SDD", "power_type": "solar"}
]

#: THE PACKAGED DEFAULT LOGGER CATALOG: three RTMDs from three manufacturers,
#: enough to exercise device metadata without shipping the whole E006 list. See
#: `pqs_e006_rtmds` / `Catalogs.builtin('pqs-e003-full')` for that.
rtmds = [
    {"LPQS":"E006/019", "type": "Remote Temperature Monitoring Device","LMFR":"Berlinger & Co. AG", "LMOD":"SmartLine"},
    {"LPQS":"E006/039", "type": "Remote Temperature Monitoring Device","LMFR":"Nexleaf Analytics", "LMOD":"ColdTrace 5"},
    {"LPQS":"E006/060", "type": "Remote Temperature Monitoring Device","LMFR":"Qingdao Haier Biomedical Co., Ltd", "LMOD":"Haier U-Cool"}
]

class DeviceGroup():
    def __init__(self, device_list) -> None:
        '''
        Initialize a DeviceGroup with a list of devices.
        
        For example:
            dg = DeviceGroup(fridges)
          
        or
            dg = DeviceGroup(rtmds)
        '''
        self.devices = device_list
        # Validate every explicit power_type up front, so a bad value in a
        # user-supplied catalog fails at load rather than whenever the random
        # draw happens to land on that record.
        for device_dict in self.devices:
            if 'power_type' in device_dict:
                validate_power_type(device_dict['power_type'], device_label(device_dict))

    def random_device(self, manufacturer=None):
        '''
        Return metadata for a random device. If manufacturer is specified,
        return a random device from that manufacturer.
        '''
        if manufacturer is None:
            devices = self.devices
        else:
            devices = self.get_manufacturer_group(manufacturer)
            if len(devices) == 0:
                print(f"Manufacturer {manufacturer} not found. Selecting randomly.")
                devices = self.devices
    
        return Device.from_dict(random.choice(devices))
    
    def list(self):
        '''Return a list of all devices'''
        return self.devices
    
    def group_by_manufacturer(self):
        '''Return a dictionary of devices grouped by manufacturer'''
        groups = {}
        for device_dict in self.devices:
            groups.setdefault(device_manufacturer(device_dict), []).append(device_dict)
        return groups

    def get_random_manufacturer(self):
        '''Return a random manufacturer name'''
        return random.choice(list(self.group_by_manufacturer().keys()))
                             
    def get_manufacturer_group(self, manufacturer=None):
        '''
        Return a list of devices from a specified manufacturer (regex
        matching). Otherwise, select a random manufacturer and return
        the corresponding device group.
        '''
        group = self.group_by_manufacturer()
        if manufacturer is None:
            manufacturer = random.choice(list(group.keys()))
        else:
            prog = re.compile(manufacturer, re.IGNORECASE)
            manufacturers = [m for m in group.keys() if prog.search(m)]
            manufacturer = random.choice(manufacturers)

        return group[manufacturer]
