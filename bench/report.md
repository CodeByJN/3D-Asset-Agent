| Task | Side | Make: time | Make: tokens processed | Make: new tokens | Make: calls | Revise: time | Revise: tokens processed | Revise: new tokens | Revise: calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Palm tree | native | 73s | 337k | 61k | 6 | 29s | 181k | 3k | 3 |
| Palm tree | harness | 822s | 1.44M | 93k | 23 | 199s | 1.46M | 14k | 19 |
| Super Saiyan aura | native | 388s | 1.45M | 48k | 22 | 54s | 740k | 10k | 8 |
| Super Saiyan aura | harness | 751s | 4.32M | 88k | 52 | 65s | 1.07M | 9k | 9 |
| R15 run cycle | native | 125s | 540k | 33k | 12 | 36s | 343k | 5k | 5 |
| R15 run cycle | harness | 98s | 469k | 31k | 9 | 50s | 340k | 7k | 6 |
| **All three** | **native** | **586s** | **2.32M** | **142k** | **40** | **119s** | **1.26M** | **18k** | **16** |
| **All three** | **harness** | **1671s** | **6.22M** | **212k** | **84** | **313s** | **2.87M** | **30k** | **34** |

| Output | Native v1 → v2 | Harness v1 → v2 |
|---|---|---|
| Palm tris | 650 → 650 | 1426 → 1422 |
| Palm height | 14.3 → 21.4 | 4.0 → 5.9 |
| Palm materials | 5 → 5 | 1 → 1 |
| Aura ParticleEmitter | 19 → 19 | 12 → 12 |
| Aura Beam | 70 → 70 | 0 → 0 |
| Aura total_rate | 647 → 647 | 635 → 635 |
| Run length | 0.7s → 0.5s | 0.8s → 0.6s |
| Run keyframes | 13 → 13 | 9 → 9 |
