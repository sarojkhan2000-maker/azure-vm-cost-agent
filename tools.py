from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from datetime import datetime, timedelta, timezone
import statistics
from langchain.tools import tool

# Azure authentication
credential = DefaultAzureCredential()
subscription_id = "b270152d-52bb-4cd9-af01-aa6961faf1ad"

compute_client = ComputeManagementClient(credential, subscription_id)
monitor_client = MonitorManagementClient(credential, subscription_id)


def normalize_vm_size(vm_size):
    """
    Converts Azure SDK enum/string VM size into clean string.
    Example:
    VirtualMachineSizeTypes.STANDARD_D2_S_V3 -> Standard_D2s_v3
    """
    if hasattr(vm_size, "value"):
        return vm_size.value
    return str(vm_size)


def get_idle_vms_logic(query: str = "") -> str:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)

    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    timespan = f"{start_str}/{end_str}"
    interval = "PT1H"

    results = []

    for vm in compute_client.virtual_machines.list_all():
        vm_id_parts = vm.id.split("/")
        resource_group = vm_id_parts[4]
        vm_name = vm.name
        vm_size = normalize_vm_size(vm.hardware_profile.vm_size)

        metrics_data = monitor_client.metrics.list(
            resource_uri=vm.id,
            timespan=timespan,
            interval=interval,
            metricnames="Percentage CPU",
            aggregation="Average"
        )

        cpu_values = []

        for series in metrics_data.value:
            for point in series.timeseries:
                for datapoint in point.data:
                    if datapoint.average is not None:
                        cpu_values.append(datapoint.average)

        if cpu_values:
            avg_cpu = round(statistics.mean(cpu_values), 2)

            if avg_cpu < 6.0:
                results.append(
                    f"VM: {vm_name} | Resource Group: {resource_group} | Size: {vm_size} | Avg CPU: {avg_cpu}%"
                )

    if not results:
        return "No idle VMs found."

    return "The following VMs are idle (CPU <6% over 7 days):\n" + "\n".join(results)


@tool
def get_idle_vms(query: str = "") -> str:
    """
    Returns a list of Azure VMs that have average CPU below 6% over the last 7 days.
    """
    return get_idle_vms_logic(query)


@tool
def resize_vm(
    vm_name: str,
    resource_group: str,
    target_size: str,
    approval: str = "no"
) -> str:
    """
    Resizes an Azure VM only after explicit human approval.
    approval must be exactly 'yes' to execute the resize.
    """

    price_table = {
    "Standard_D2s_v3": 0.096,
    "Standard_D2lds_v5": 0.075,

    "Standard_B1s": 0.0104,
    "Standard_B1ms": 0.0208,
    "Standard_B2s": 0.0416,
    "Standard_B2ms": 0.0832,

    "Standard_F1s": 0.040,
    "Standard_F1": 0.040,

    "Standard_A1_v2": 0.025,
    "Standard_A2_v2": 0.050
}

    try:
        vm = compute_client.virtual_machines.get(resource_group, vm_name)

        current_size = normalize_vm_size(vm.hardware_profile.vm_size)

        if current_size == target_size:
            return f"VM {vm_name} is already using size {target_size}. No resize needed."

        if current_size not in price_table:
            return f"Current VM size {current_size} is not in demo price table. Add it first."

        if target_size not in price_table:
            return f"Target VM size {target_size} is not in demo price table. Add it first."

        current_price = price_table[current_size]
        target_price = price_table[target_size]

        monthly_hours = 730
        current_monthly = round(current_price * monthly_hours, 2)
        target_monthly = round(target_price * monthly_hours, 2)
        savings = round(current_monthly - target_monthly, 2)

        preview = f"""
Resize Plan:
VM Name: {vm_name}
Resource Group: {resource_group}
Current Size: {current_size}
Target Size: {target_size}

Approx Current Monthly Cost: ${current_monthly}
Approx Target Monthly Cost: ${target_monthly}
Approx Monthly Savings: ${savings}

Approval Required:
To execute resize, call this tool again with approval='yes'.
"""

        if approval.lower().strip() != "yes":
            return preview + "\nResize NOT executed because approval was not 'yes'."

        compute_client.virtual_machines.begin_deallocate(
            resource_group,
            vm_name
        ).result()

        vm.hardware_profile.vm_size = target_size

        compute_client.virtual_machines.begin_create_or_update(
            resource_group,
            vm_name,
            vm
        ).result()

        compute_client.virtual_machines.begin_start(
            resource_group,
            vm_name
        ).result()

        return f"""
Resize completed successfully.

VM Name: {vm_name}
Resource Group: {resource_group}
Old Size: {current_size}
New Size: {target_size}
Approx Monthly Savings: ${savings}
"""

    except Exception as e:
        return f"Resize failed: {str(e)}"
