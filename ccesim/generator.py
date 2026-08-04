from uuid import uuid4
from datetime import datetime
import pytz

from ccesim.schemas import SCHEMA_VERSION, TRANSFER_SRC


def random_serial():
    return uuid4().hex


def random_amid():
    """Supplier-internal Appliance Monitoring ID (AMID).

    Per cce-interop, AMID is the appliance's ID in the RTMD supplier's cloud
    platform -- a stable reference that is deliberately NOT the serial/asset
    number. A random 12-hex token (e.g. '4bb74045097e') matches the schema
    examples; mint once per device and reuse across reports to keep it stable.
    """
    return uuid4().hex[:12]


def transfer_metadata(type='rtmd', callback_url=None, schema_version=None,
                      transfer_src=None):
    """Build the transmission metadata envelope.

    `schema_version` overrides the declared cce-interop version; None keeps the
    packaged default. It relabels the transmission only -- the records are
    still generated the same way -- so an employer system pinned to an older
    version may still reject the payload on its own merits.

    `transfer_src` overrides the data transmission source (the URI identifying
    the data supplier the delivery is attributed to); None keeps the packaged
    default. It re-attributes the transmission only -- the records are
    unchanged -- and one value applies to the whole run.
    """
    obj = {
        'transferId': str(uuid4()),
        'transferSrc': transfer_src or TRANSFER_SRC,
        'transferredAt': datetime.now(pytz.utc),
        'transferType': 'rtm',
        'schemaVersion': schema_version or SCHEMA_VERSION,
    }
    if type == 'ems':
        obj['transferType'] = 'ems'

    # Per cce-interop, the webhook field is 'transferCallbackUrl' (a non-nullable
    # string). Include it only when a URL is supplied; omit it entirely otherwise.
    if callback_url is not None:
        obj['transferCallbackUrl'] = callback_url

    return obj
