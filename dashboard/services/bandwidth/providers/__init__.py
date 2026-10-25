from typing import Dict, Type
from dashboard.services.bandwidth.base import BaseISPProvider
from dashboard.services.bandwidth.providers.biznet import BiznetProvider
from dashboard.services.bandwidth.providers.manual import ManualProvider
from dashboard.services.bandwidth.providers.indihome import IndiHomeProvider

AVAILABLE_PROVIDERS: Dict[str, Type[BaseISPProvider]] = {
    BiznetProvider.provider_id: BiznetProvider,
    ManualProvider.provider_id: ManualProvider,
    IndiHomeProvider.provider_id: IndiHomeProvider,
}

def get_provider_classes() -> Dict[str, Type[BaseISPProvider]]:
    return dict(AVAILABLE_PROVIDERS)
