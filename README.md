# HomeRing

HomeRing is a landline call blocker designed for seniors. It intercepts incoming calls, screens them against known scam/spam numbers, and alerts family members via a mobile app — giving seniors peace of mind without changing how they use their phone.

## Project Structure

| Folder | Description |
|--------|-------------|
| `/device` | Raspberry Pi code — handles call interception, caller ID detection, and hardware control |
| `/cloud` | AWS Lambda functions — manages blocklist sync, notifications, and call logging |
| `/app` | React Native mobile app — lets family members manage the blocklist and view call history |
| `/docs` | Documentation — architecture diagrams, setup guides, and API references |
| `/tests` | Test scripts — unit and integration tests for all components |

## How It Works

1. A call comes in on the landline
2. The Raspberry Pi device intercepts the call and reads the caller ID
3. It checks the number against a blocklist stored in AWS
4. Blocked calls are silently dropped; unknown calls are flagged for review
5. Family members are notified via the mobile app and can approve/block numbers remotely

## Getting Started

See [`/docs`](./docs) for setup instructions for each component.

## License

MIT
