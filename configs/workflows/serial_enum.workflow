{
  "version": "1.0",
  "name": "Serial Device Enumeration",
  "description": "Switch to serial gadget, send an AT probe sequence, and wait for a response.",
  "trigger": { "type": "manual", "params": {} },
  "blocks": [
    {
      "id": "c1000001",
      "type": "gadget_switch_serial",
      "enabled": true,
      "params": {}
    },
    {
      "id": "c1000002",
      "type": "delay",
      "enabled": true,
      "params": { "ms": 1500 }
    },
    {
      "id": "c1000003",
      "type": "serial_send_string",
      "enabled": true,
      "params": { "text": "AT\r\n", "delay_ms": 50 }
    },
    {
      "id": "c1000004",
      "type": "serial_wait_response",
      "enabled": true,
      "params": { "pattern": "OK", "timeout_ms": 3000 }
    },
    {
      "id": "c1000005",
      "type": "serial_send_string",
      "enabled": true,
      "params": { "text": "ATI\r\n", "delay_ms": 50 }
    },
    {
      "id": "c1000006",
      "type": "serial_wait_response",
      "enabled": true,
      "params": { "pattern": "OK", "timeout_ms": 3000 }
    },
    {
      "id": "c1000007",
      "type": "serial_send_string",
      "enabled": true,
      "params": { "text": "AT+CGMI\r\n", "delay_ms": 50 }
    },
    {
      "id": "c1000008",
      "type": "serial_wait_response",
      "enabled": true,
      "params": { "pattern": "OK", "timeout_ms": 3000 }
    }
  ]
}
