proxmox_endpoint  = "{{ proxmox_endpoint | default('https://192.168.0.100:8006/', true) }}"
proxmox_api_token = "{{ proxmox_api_token | default('CHANGE_ME', true) }}"
proxmox_insecure  = {{ proxmox_insecure | default('false', true) | lower }}

# 全局默认 qcow2 镜像。
default_image_file_id = "{{ default_image_file_id | default('local:import/debian-12-genericcloud-amd64.qcow2', true) }}"

# 全局默认登录信息。
default_username = "{{ default_username | default('debian', true) }}"
# 默认不提供密码；请显式传入强密码或优先使用 SSH Key。
default_password = {% if default_password is defined and default_password %}"{{ default_password }}"{% else %}null{% endif %}

default_ssh_public_keys = [
  "{{ default_ssh_public_key | default('ssh-ed25519 CHANGE_ME user@host', true) }}"
]

vms = {
  "{{ vm_key | default('debian', true) }}" = {
    name      = "{{ vm_name | default('debian', true) }}"
    node_name = "{{ vm_node_name | default('pve', true) }}"
    vm_id     = {{ vm_id | default('201', true) }}
    pool_id   = "{{ vm_pool_id | default('Temp_Pool', true) }}"

    tags = {{ vm_tags_hcl | default('["debian", "autoopshub", "Oversee"]', true) }}

    cpu_cores = {{ vm_cpu_cores | default('4', true) }}
    memory_mb = {{ vm_memory_mb | default('4096', true) }}

    network_devices = [
      {
        bridge   = "{{ vm_bridge | default('vmbr0', true) }}"
        model    = "{{ vm_network_model | default('virtio', true) }}"
        firewall = {{ vm_firewall | default('true', true) | lower }}
      }
    ]

    ip_configs = [
      {
        method  = "{{ vm_ip_method | default('dhcp', true) }}"
        address = {% if vm_ip_method | default('dhcp', true) == 'static' %}"{{ vm_static_address | default('192.168.0.201', true) }}"{% else %}null{% endif %}
        cidr    = {% if vm_ip_method | default('dhcp', true) == 'static' %}{{ vm_static_cidr | default('24', true) }}{% else %}null{% endif %}
        gateway = {% if vm_ip_method | default('dhcp', true) == 'static' %}"{{ vm_static_gateway | default('192.168.0.1', true) }}"{% else %}null{% endif %}
      }
    ]

    disks = [
      {
        interface    = "{{ vm_disk_interface | default('scsi0', true) }}"
        datastore_id = "{{ vm_disk_datastore_id | default('VM-Data_1', true) }}"
        size_gb      = {{ vm_disk_size_gb | default('40', true) }}
      }
    ]
  }
}
