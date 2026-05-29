from onikiri.modules.bluetooth_recon import BluetoothReconModule
from onikiri.modules.engagement import EngagementModule
from onikiri.modules.engagement_export import EngagementExportModule
from onikiri.modules.gadget_automation import GadgetAutomationModule
from onikiri.modules.hid_gadget import HidGadgetModule
from onikiri.modules.mitm import MitmModule
from onikiri.modules.network_scanner import NetworkScannerModule
from onikiri.modules.payload_builder import PayloadBuilderModule
from onikiri.modules.system_info import SystemInfoModule
from onikiri.modules.wifi_recon import WifiReconModule

MODULE_TYPES = {
    "wifi_recon": WifiReconModule,
    "mitm": MitmModule,
    "network_scanner": NetworkScannerModule,
    "bluetooth_recon": BluetoothReconModule,
    "hid_gadget": HidGadgetModule,
    "gadget_automation": GadgetAutomationModule,
    "payload_builder": PayloadBuilderModule,
    "engagement": EngagementModule,
    "engagement_export": EngagementExportModule,
    "system_info": SystemInfoModule,
}
