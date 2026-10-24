## DEVStone-like: simulation wall clock (ms, warm median)

| config | transitions | devspy@0857ff6 | devspy@0857ff6+quick-wins | devsjava | devsjava[-XX:+UseSerialGC -Xmx128m] |
|---|---|---|---|---|---|
| 5x3, 1000 ev | 28000 | 153 | 112 | 121 | 68 |
| 10x10, 1000 ev | 184000 | 935 | 657 | 365 | 289 |
| 200x1, 1000 ev | 402000 | 1488 | 1037 | 565 | 486 |
| 3x50, 500 ev | 102000 | 2198 | 1508 | 651 | 564 |
| 20x20, 500 ev | 382000 | 2007 | 1272 | 667 | 581 | 

## End-to-end process (startup + build + run)

| engine | config | wall ms | peak RSS MiB |
|---|---|---|---|
| devspy@0857ff6+quick-wins | 5x3, 100 ev | 46 | 14.4 |
| devspy@0857ff6+quick-wins | 10x10, 1000 ev | 683 | 14.4 |
| devsjava | 5x3, 100 ev | 126 | 86.0 |
| devsjava | 10x10, 1000 ev | 720 | 414.5 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 5x3, 100 ev | 126 | 78.8 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 10x10, 1000 ev | 519 | 153.3 | 

## RL-style: single worker

| engine | sections | episodes | process wall ms | ms/episode | 1st episode ms | RSS MiB | decisions | reward |
|---|---|---|---|---|---|---|---|---|
| devspy@0857ff6+quick-wins | 8 | 20 | 220 | 9.23 | 9.8 | 14 | 7107 | 12823 |
| devspy@0857ff6+quick-wins | 8 | 500 | 4569 | 9.07 | 9.8 | 14 | 177978 | 320362 |
| devspy@0857ff6+quick-wins | 64 | 100 | 20979 | 209.69 | 212.0 | 14 | 284721 | 512275 |
| devsjava | 8 | 20 | 383 | 12.62 | 50.0 | 235 | 7107 | 12823 |
| devsjava | 8 | 500 | 3532 | 6.41 | 50.0 | 421 | 177978 | 320362 |
| devsjava | 64 | 100 | 22270 | 219.57 | 456.3 | 404 | 284721 | 512275 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 20 | 309 | 8.13 | 46.9 | 135 | 7107 | 12823 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 500 | 2872 | 5.21 | 47.2 | 135 | 177978 | 320362 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 64 | 100 | 17456 | 173.13 | 260.8 | 114 | 284721 | 512275 | 

## RL-style: parallel workers (8 sections, 200 episodes/worker)

| engine | workers | wall ms | episodes/s | total RSS MiB |
|---|---|---|---|---|
| devspy@0857ff6+quick-wins | 1 | 1861 | 107 | 14 |
| devspy@0857ff6+quick-wins | 4 | 1932 | 414 | 56 |
| devspy@0857ff6+quick-wins | 8 | 1942 | 824 | 112 |
| devspy@0857ff6+quick-wins | 16 | 2889 | 1108 | 224 |
| devsjava | 1 | 1616 | 124 | 420 |
| devsjava | 4 | 2246 | 356 | 1694 |
| devsjava | 8 | 3549 | 451 | 3384 |
| devsjava | 16 | 6597 | 485 | 6726 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 1 | 1306 | 153 | 148 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 4 | 1791 | 447 | 573 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 2834 | 565 | 1153 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 16 | 5575 | 574 | 2294 |
