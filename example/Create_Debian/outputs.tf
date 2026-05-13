locals {
  # qemu-guest-agent 回传的 IPv4，过滤掉 lo 环回地址。
  agent_ipv4_addresses_filtered = {
    for vm_key, vm in proxmox_virtual_environment_vm.vm : vm_key => [
      for ip in flatten(vm.ipv4_addresses) : ip
      if ip != "127.0.0.1"
    ]
  }

  # 静态声明 IP + guest-agent 回传 IP 的合并集合，过滤空值并去重。
  all_ipv4_addresses_filtered = distinct(compact(concat(
    local.configured_static_ipv4,
    flatten(values(local.agent_ipv4_addresses_filtered))
  )))
}

output "vm_ids" {
  description = "VM ID 映射"
  value = {
    for k, vm in proxmox_virtual_environment_vm.vm : k => vm.vm_id
  }
}

output "vm_names" {
  description = "VM 名称映射"
  value = {
    for k, vm in proxmox_virtual_environment_vm.vm : k => vm.name
  }
}

output "vm_configured_static_ipv4" {
  description = "Terraform 声明中配置的静态 IPv4，不包含 DHCP 动态获取的 IP。"
  value       = local.configured_static_ipv4
}

output "vm_agent_ipv4_addresses" {
  description = "qemu-guest-agent 回传的 IPv4 地址，已过滤 lo 环回地址。DHCP 场景依赖 guest 内安装并运行 qemu-guest-agent。"
  value       = local.agent_ipv4_addresses_filtered
}

output "vm_ip_list" {
  description = "静态声明 IP + qemu-guest-agent 回传 IP 的合并集合，已过滤 lo 环回地址。"
  value       = local.all_ipv4_addresses_filtered
}

output "vm_ip_csv" {
  description = "单独的 IP 地址集合，以英文逗号分隔，已过滤 lo 环回地址。"
  value       = join(",", local.all_ipv4_addresses_filtered)
}