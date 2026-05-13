terraform {
  required_version = ">= 1.5.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.70"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure
}

locals {
  # 每台 VM 的有效账号信息：局部优先，全局兜底。
  vm_effective_user = {
    for vm_key, vm in var.vms : vm_key => {
      username        = coalesce(vm.username, var.default_username)
      password        = coalesce(vm.password, var.default_password)
      ssh_public_keys = coalesce(vm.ssh_public_keys, var.default_ssh_public_keys)
    }
  }

  # 静态 IP 是 Terraform 声明里确定存在的；
  # DHCP IP 需要依赖 qemu-guest-agent 回传。
  configured_static_ipv4 = flatten([
    for vm_key, vm in var.vms : [
      for ip in vm.ip_configs : ip.address
      if ip.method == "static"
    ]
  ])
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = var.vms

  name        = each.value.name
  description = coalesce(each.value.description, "Managed by Terraform")
  tags        = sort(distinct(each.value.tags))

  node_name = each.value.node_name
  vm_id     = each.value.vm_id
  pool_id   = each.value.pool_id

  started         = each.value.started
  on_boot         = each.value.on_boot
  bios            = each.value.bios
  machine         = each.value.machine
  scsi_hardware   = each.value.scsi_hardware
  stop_on_destroy = each.value.stop_on_destroy

  agent {
    enabled = each.value.qemu_agent_enabled

    wait_for_ip {
      ipv4 = each.value.wait_for_ipv4
    }
  }

  cpu {
    cores   = each.value.cpu_cores
    sockets = each.value.cpu_sockets
    type    = each.value.cpu_type
  }

  memory {
    dedicated = each.value.memory_mb
    floating  = each.value.memory_ballooning ? each.value.memory_mb : null
  }

  operating_system {
    type = each.value.os_type
  }

  dynamic "efi_disk" {
    for_each = each.value.bios == "ovmf" ? [1] : []

    content {
      datastore_id      = each.value.efi_datastore_id
      file_format       = each.value.efi_file_format
      type              = each.value.efi_type
      pre_enrolled_keys = each.value.efi_pre_enrolled_keys
    }
  }

  dynamic "tpm_state" {
    for_each = each.value.enable_tpm ? [1] : []

    content {
      datastore_id = each.value.tpm_datastore_id
      version      = each.value.tpm_version
    }
  }

  initialization {
    datastore_id = each.value.cloudinit_datastore_id

    dynamic "ip_config" {
      for_each = each.value.ip_configs

      content {
        ipv4 {
          address = ip_config.value.method == "dhcp" ? "dhcp" : "${ip_config.value.address}/${ip_config.value.cidr}"
          gateway = ip_config.value.method == "dhcp" ? null : ip_config.value.gateway
        }
      }
    }

    dns {
      domain  = each.value.dns_domain
      servers = each.value.dns_servers
    }

    user_account {
      username = local.vm_effective_user[each.key].username
      password = local.vm_effective_user[each.key].password
      keys     = local.vm_effective_user[each.key].ssh_public_keys
    }
  }

  dynamic "network_device" {
    for_each = each.value.network_devices

    content {
      bridge      = network_device.value.bridge
      model       = network_device.value.model
      vlan_id     = network_device.value.vlan_id
      mac_address = network_device.value.mac_address
      firewall    = network_device.value.firewall
      mtu         = network_device.value.mtu
      queues      = network_device.value.queues
    }
  }

  dynamic "disk" {
    for_each = {
      for idx, d in each.value.disks : idx => d
    }

    content {
      datastore_id = disk.value.datastore_id
      interface    = disk.value.interface
      size         = disk.value.size_gb
      file_format  = disk.value.file_format
      discard      = disk.value.discard
      iothread     = disk.value.iothread
      ssd          = disk.value.ssd

      # 第 0 块盘作为系统盘，从 PVE 本地 qcow2/import 文件导入。
      # 其余磁盘作为空数据盘创建。
      #
      # 优先级：
      # VM 局部 image_file_id > 全局 default_image_file_id
      import_from = tonumber(disk.key) == 0 ? coalesce(
        each.value.image_file_id,
        var.default_image_file_id
      ) : null
    }
  }

  dynamic "serial_device" {
    for_each = each.value.enable_serial_console ? [1] : []

    content {
      device = "socket"
    }
  }

  lifecycle {
    precondition {
      condition = coalesce(
        each.value.image_file_id,
        var.default_image_file_id
      ) != null

      error_message = "每台 VM 必须能获得 qcow2 镜像来源：vm.image_file_id 或 var.default_image_file_id 至少一个不为空。"
    }
  }
}