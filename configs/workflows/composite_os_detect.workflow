{
  "version": "1.0",
  "name": "OS-Adaptive Composite Profile",
  "description": "Detects OS hint and switches to the most suitable gadget profile.",
  "trigger": { "type": "usb_hid", "params": {} },
  "blocks": [
    {
      "id": "b1000001",
      "type": "wait_event",
      "enabled": true,
      "params": { "event": "hid_active", "timeout_ms": 8000 }
    },
    {
      "id": "b1000002",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 500 }
    },
    {
      "id": "b1000003",
      "type": "if_os",
      "enabled": true,
      "params": { "os": "windows" }
    },
    {
      "id": "b1000004",
      "type": "gadget_switch_composite",
      "enabled": true,
      "params": { "functions": "hid,serial" }
    },
    {
      "id": "b1000005",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 1200 }
    },
    {
      "id": "b1000006",
      "type": "hid_type_text",
      "enabled": true,
      "params": { "text": "echo Windows target\r\n", "delay_ms": 30 }
    },
    {
      "id": "b1000007",
      "type": "else_block",
      "enabled": true,
      "params": {}
    },
    {
      "id": "b1000008",
      "type": "if_os",
      "enabled": true,
      "params": { "os": "linux" }
    },
    {
      "id": "b1000009",
      "type": "gadget_switch_composite",
      "enabled": true,
      "params": { "functions": "hid,ethernet" }
    },
    {
      "id": "b1000010",
      "type": "else_block",
      "enabled": true,
      "params": {}
    },
    {
      "id": "b1000011",
      "type": "gadget_switch_hid",
      "enabled": true,
      "params": { "mouse": true }
    },
    {
      "id": "b1000012",
      "type": "end_if",
      "enabled": true,
      "params": {}
    },
    {
      "id": "b1000013",
      "type": "end_if",
      "enabled": true,
      "params": {}
    }
  ]
}
