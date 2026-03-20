<p align="center">
  <img src="../banner_2.jpg" alt="ResQNet Banner" width="100%"/>
</p>

> **Operator dashboard and control interface for the ResQNet platform.**

The WebApp provides a real-time dashboard for search-and-rescue operators, displaying live maps, heatmaps, drone feeds, and rescue strategies.

---

## Features

- Interactive map with geolocation zone selection
- Real-time danger, density, and rescue priority heatmap overlays
- Live drone feed viewer
- Rescue strategy and escape route display
- Disaster monitoring alerts panel
- Officer rescue plan viewer
- Field safety instruction broadcaster
- Alarm notifications for medical emergencies and threats

---

## Integration with Reasoning Agent

The WebApp communicates with the Reasoning Agent via REST APIs:

| Agent Endpoint | WebApp Usage |
|---|---|
| `POST /api/agent/chat` | Chat interface for the unified agent |
| `GET /api/search/alarms` | Poll for medical/threat alarms |
| `GET /api/monitor/alerts` | Display disaster monitoring alerts |
| `GET /api/scout/zones` | Render zone grid on map |
| `POST /api/scout/strategy` | Display rescue strategy |
| `POST /api/rescue/safety_instructions` | Show safety instructions |
| `POST /api/rescue/operator_suggestions` | Show operator action suggestions |

---

## Status

Under Development -- UI framework and component structure to be defined.

## Contact and Credits

Developed by **Mokhtar Ouardi**, **Adas Aburaya** and **Anas Aburaya** for the vhack Hackathon.

- **Mokhtar Ouardi**: [GitHub](https://github.com/MokhtarOuardi) | [Email](mailto:m.ouardi@graduate.utm.my)
- **Anas Aburaya**: [GitHub](https://github.com/Shadowpasha) | [Email](mailto:ameranas1923@gmail.com)
- **Adam Aburaya**: [GitHub](https://github.com/adam) | [Email](mailto:@gmail.com)

---
© 2026 ResQnet Team. All rights reserved.
