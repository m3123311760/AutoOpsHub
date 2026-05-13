variable "proxmox_endpoint" {
  description = "PVE API 地址，例如 https://192.168.0.10:8006/"
  type        = string
}

variable "proxmox_api_token" {
  description = "PVE API Token，格式一般为 user@realm!tokenid=token-secret"
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "是否允许自签名证书"
  type        = bool
  default     = false
}

variable "default_image_file_id" {
  description = "默认使用的 PVE 本地 qcow2 文件 ID，例如 local:import/debian-12-genericcloud-amd64.qcow2。VM 局部 image_file_id 优先级更高。"
  type        = string
  default     = null
}

variable "default_username" {
  description = "默认 Cloud-Init 用户名。VM 局部 username 优先级更高。"
  type        = string
  default     = "debian"
}

variable "default_password" {
  description = "默认 Cloud-Init 密码。VM 局部 password 优先级更高。生产建议改用 SSH Key。"
  type        = string
  default     = null
  sensitive   = true
}

variable "default_ssh_public_keys" {
  description = "默认 SSH 公钥列表。VM 局部 ssh_public_keys 优先级更高。"
  type        = list(string)
  default     = []
}

variable "vms" {
  description = "VM 声明集合。key 是 Terraform 内部标识，name 是 PVE 里的 VM 名称。"

  type = map(object({
    name        = string
    description = optional(string)

    node_name = string
    vm_id     = optional(number)
    pool_id   = optional(string)

    tags = optional(list(string), ["terraform"])

    started = optional(bool, true)
    on_boot = optional(bool, true)

    # 镜像来源：
    # 使用已经存在于 PVE 的 local:import/xxx.qcow2。
    #
    # 优先级：
    # VM 局部 image_file_id > 全局 default_image_file_id。
    image_file_id = optional(string)

    # 局部账号信息，优先级高于全局 default_xxx。
    username        = optional(string)
    password        = optional(string)
    ssh_public_keys = optional(list(string))

    cpu_cores   = optional(number, 2)
    cpu_sockets = optional(number, 1)
    cpu_type    = optional(string, "x86-64-v2-AES")

    memory_mb         = optional(number, 2048)
    memory_ballooning = optional(bool, false)

    os_type = optional(string, "l26")

    bios          = optional(string, "seabios")
    machine       = optional(string, "pc")
    scsi_hardware = optional(string, "virtio-scsi-pci")

    qemu_agent_enabled = optional(bool, true)
    wait_for_ipv4      = optional(bool, true)
    stop_on_destroy    = optional(bool, true)

    cloudinit_datastore_id = optional(string, "local-lvm")

    dns_domain  = optional(string)
    dns_servers = optional(list(string), [])

    enable_serial_console = optional(bool, true)

    enable_tpm       = optional(bool, false)
    tpm_datastore_id = optional(string, "local-lvm")
    tpm_version      = optional(string, "v2.0")

    efi_datastore_id      = optional(string, "local-lvm")
    efi_file_format       = optional(string, "raw")
    efi_type              = optional(string, "4m")
    efi_pre_enrolled_keys = optional(bool, false)

    network_devices = optional(list(object({
      bridge      = optional(string, "vmbr0")
      model       = optional(string, "virtio")
      vlan_id     = optional(number)
      mac_address = optional(string)
      firewall    = optional(bool, false)
      mtu         = optional(number)
      queues      = optional(number)
      })), [
      {
        bridge = "vmbr0"
        model  = "virtio"
      }
    ])

    # 和 network_devices 一一对应。
    #
    # DHCP:
    #   {
    #     method = "dhcp"
    #   }
    #
    # 静态:
    #   {
    #     method  = "static"
    #     address = "192.168.0.101"
    #     cidr    = 24
    #     gateway = "192.168.0.1"
    #   }
    ip_configs = optional(list(object({
      method  = string
      address = optional(string)
      cidr    = optional(number)
      gateway = optional(string)
      })), [
      {
        method = "dhcp"
      }
    ])

    # 第 0 块盘会从 qcow2 导入，作为系统盘；
    # 后面的盘会作为空数据盘创建。
    disks = list(object({
      datastore_id = optional(string, "local-lvm")
      interface    = string
      size_gb      = number
      file_format  = optional(string, "raw")
      discard      = optional(string, "on")
      iothread     = optional(bool, true)
      ssd          = optional(bool, true)
    }))
  }))

  validation {
    condition = alltrue([
      for _, vm in var.vms : length(vm.disks) >= 1
    ])
    error_message = "每台 VM 至少要声明 1 块磁盘，第 0 块磁盘会作为 qcow2 导入的系统盘。"
  }

  validation {
    condition = alltrue([
      for _, vm in var.vms : length(vm.network_devices) == length(vm.ip_configs)
    ])
    error_message = "network_devices 与 ip_configs 必须一一对应，长度必须一致。"
  }

  validation {
    condition = alltrue(flatten([
      for _, vm in var.vms : [
        for ip in vm.ip_configs : contains(["dhcp", "static"], ip.method)
      ]
    ]))
    error_message = "ip_configs[*].method 只能是 dhcp 或 static。"
  }

  validation {
    condition = alltrue(flatten([
      for _, vm in var.vms : [
        for ip in vm.ip_configs :
        ip.method == "dhcp" || (
          ip.address != null &&
          ip.cidr != null &&
          ip.gateway != null
        )
      ]
    ]))
    error_message = "静态 IP 必须同时声明 address、cidr、gateway。"
  }
}
