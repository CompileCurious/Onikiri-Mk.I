{
  "version": "1.0",
  "name": "OS Probe and Respond",
  "description": "Probe OS via HID timing / driver response patterns and branch behaviour accordingly.",
  "trigger": { "type": "usb_hid", "params": {} },
  "blocks": [
    {
      "id": "d1000001",
      "type": "wait_event",
      "enabled": true,
      "params": { "event": "hid_active", "timeout_ms": 12000 }
    },
    {
      "id": "d1000002",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 2000 }
    },
    {
      "id": "d1000003",
      "type": "if_os",
      "enabled": true,
      "params": { "os": "windows" }
    },
    {
      "id": "d1000004",
      "type": "hid_key_combo",
      "enabled": true,
      "params": { "modifiers": "win", "key": "r" }
    },
    {
      "id": "d1000005",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 700 }
    },
    {
      "id": "d1000006",
      "type": "hid_type_text",
      "enabled": true,
      "params": { "text": "powershell -w hidden -nop -c \"$env:OS\"", "delay_ms": 25 }
    },
    {
      "id": "d1000007",
      "type": "hid_press_key",
      "enabled": true,
      "params": { "key": "enter" }
    },
    {
      "id": "d1000008",
      "type": "else_block",
      "enabled": true,
      "params": {}
    },
    {
      "id": "d1000009",
      "type": "if_os",
      "enabled": true,
      "params": { "os": "macos" }
    },
    {
      "id": "d1000010",
      "type": "hid_key_combo",
      "enabled": true,
      "params": { "modifiers": "meta", "key": "space" }
    },
    {
      "id": "d1000011",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 600 }
    },
    {
      "id": "d1000012",
      "type": "hid_type_text",
      "enabled": true,
      "params": { "text": "Terminal", "delay_ms": 50 }
    },
    {
      "id": "d1000013",
      "type": "hid_press_key",
      "enabled": true,
      "params": { "key": "enter" }
    },
    {
      "id": "d1000014",
      "type": "else_block",
      "enabled": true,
      "params": {}
    },
    {
      "id": "d1000015",
      "type": "hid_key_combo",
      "enabled": true,
      "params": { "modifiers": "ctrl", "key": "alt_l" }
    },
    {
      "id": "d1000016",
      "type": "hid_press_key",
      "enabled": true,
      "params": { "key": "t" }
    },
    {
      "id": "d1000017",
      "type": "end_if",
      "enabled": true,
      "params": {}
    },
    {
      "id": "d1000018",
      "type": "end_if",
      "enabled": true,
      "params": {}
    },
    {
      "id": "d1000019",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 1200 }
    },
    {
      "id": "d1000020",
      "type": "stop_workflow",
      "enabled": true,
      "params": {}
    }
  ]
}
