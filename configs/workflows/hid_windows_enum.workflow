{
  "version": "1.0",
  "name": "HID Windows Enumeration",
  "description": "Wait for HID enumeration on Windows, then type a basic command.",
  "trigger": { "type": "usb_hid", "params": {} },
  "blocks": [
    {
      "id": "a1b2c3d4",
      "type": "wait_event",
      "enabled": true,
      "params": { "event": "hid_active", "timeout_ms": 10000 }
    },
    {
      "id": "a1b2c3d5",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 1500 }
    },
    {
      "id": "a1b2c3d6",
      "type": "hid_key_combo",
      "enabled": true,
      "params": { "modifiers": "win", "key": "r" }
    },
    {
      "id": "a1b2c3d7",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 800 }
    },
    {
      "id": "a1b2c3d8",
      "type": "hid_type_text",
      "enabled": true,
      "params": { "text": "cmd.exe", "delay_ms": 40 }
    },
    {
      "id": "a1b2c3d9",
      "type": "hid_press_key",
      "enabled": true,
      "params": { "key": "enter" }
    },
    {
      "id": "a1b2c3da",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 1000 }
    },
    {
      "id": "a1b2c3db",
      "type": "hid_type_text",
      "enabled": true,
      "params": { "text": "systeminfo\r\n", "delay_ms": 30 }
    }
  ]
}
