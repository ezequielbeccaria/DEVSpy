## DEVStone-like: simulation wall clock (ms, warm median)

| config | transitions | devspy@eb23a82 | devspy@0857ff6 | devspy[devspy-mypyc] | devsjava | xdevs | xdevs-flat | pypdevs-minimal | adevs | cadmium | devsjava[-XX:+UseSerialGC -Xmx128m] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5x3, 1000 ev | 28000 | 112 | 154 | 98 | 120 | 99 | 65 | 28 | 3 | 1 | 61 |
| 10x10, 1000 ev | 184000 | 642 | 996 | 608 | 370 | 616 | 381 | 154 | 25 | 7 | 307 |
| 200x1, 1000 ev | 402000 | 1033 | 1480 | 966 | 547 | 882 | 863 | 333 | 53 | 12 | 492 |
| 3x50, 500 ev | 102000 | 1603 | 2223 | 1579 | 657 | 807 | 231 | 90 | 25 | 6 | 567 |
| 20x20, 500 ev | 382000 | 1238 | 2011 | 1159 | 687 | 1475 | 803 | 325 | 70 | 15 | 583 | 

## End-to-end process (startup + build + run)

| engine | config | wall ms | peak RSS MiB |
|---|---|---|---|
| devspy@eb23a82 | 5x3, 100 ev | 48 | 14.0 |
| devspy@eb23a82 | 10x10, 1000 ev | 693 | 14.1 |
| devspy[devspy-mypyc] | 5x3, 100 ev | 47 | 14.2 |
| devspy[devspy-mypyc] | 10x10, 1000 ev | 651 | 14.4 |
| devsjava | 5x3, 100 ev | 130 | 85.5 |
| devsjava | 10x10, 1000 ev | 739 | 405.1 |
| xdevs | 5x3, 100 ev | 77 | 23.2 |
| xdevs | 10x10, 1000 ev | 701 | 23.5 |
| pypdevs-minimal | 5x3, 100 ev | 23 | 11.4 |
| pypdevs-minimal | 10x10, 1000 ev | 179 | 11.5 |
| adevs | 5x3, 100 ev | 2 | 3.8 |
| adevs | 10x10, 1000 ev | 27 | 3.9 |
| cadmium | 5x3, 100 ev | 2 | 3.8 |
| cadmium | 10x10, 1000 ev | 8 | 3.9 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 5x3, 100 ev | 133 | 79.4 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 10x10, 1000 ev | 557 | 150.0 | 

## RL-style: single worker

| engine | sections | episodes | process wall ms | ms/episode | 1st episode ms | RSS MiB | decisions | reward |
|---|---|---|---|---|---|---|---|---|
| devspy@eb23a82 | 8 | 20 | 224 | 9.31 | 9.8 | 14 | 7107 | 12823 |
| devspy@eb23a82 | 8 | 500 | 4570 | 9.05 | 9.7 | 14 | 177978 | 320362 |
| devspy@eb23a82 | 64 | 100 | 21197 | 211.63 | 215.5 | 14 | 284721 | 512275 |
| devspy[devspy-mypyc] | 8 | 20 | 201 | 8.15 | 8.5 | 14 | 7107 | 12823 |
| devspy[devspy-mypyc] | 8 | 500 | 4086 | 8.09 | 8.4 | 14 | 177978 | 320362 |
| devspy[devspy-mypyc] | 64 | 100 | 21226 | 211.73 | 214.1 | 15 | 284721 | 512275 |
| devsjava | 8 | 20 | 387 | 12.84 | 51.1 | 234 | 7107 | 12823 |
| devsjava | 8 | 500 | 3650 | 6.50 | 50.8 | 415 | 177978 | 320362 |
| devsjava | 64 | 100 | 23121 | 229.04 | 456.2 | 403 | 284721 | 512275 |
| xdevs | 8 | 20 | 224 | 7.79 | 8.3 | 23 | 7107 | 12823 |
| xdevs | 8 | 500 | 3963 | 7.78 | 8.5 | 24 | 177978 | 320362 |
| xdevs | 64 | 100 | 6668 | 65.85 | 66.1 | 28 | 284721 | 512275 |
| pypdevs-minimal | 8 | 20 | 113 | 4.57 | 6.5 | 11 | 7080 | 12783 |
| pypdevs-minimal | 8 | 500 | 2297 | 4.55 | 6.4 | 12 | 177838 | 320094 |
| pypdevs-minimal | 64 | 100 | 3197 | 31.69 | 34.4 | 13 | 284697 | 512312 |
| adevs | 8 | 20 | 11 | 0.44 | 0.5 | 4 | 7107 | 12823 |
| adevs | 8 | 500 | 221 | 0.44 | 0.5 | 4 | 177978 | 320362 |
| adevs | 64 | 100 | 1505 | 15.01 | 15.3 | 4 | 284721 | 512275 |
| cadmium | 8 | 20 | 6 | 0.18 | 0.2 | 4 | 7107 | 12823 |
| cadmium | 8 | 500 | 93 | 0.18 | 0.2 | 4 | 177978 | 320362 |
| cadmium | 64 | 100 | 204 | 1.96 | 2.0 | 4 | 284721 | 512275 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 20 | 344 | 9.97 | 48.6 | 156 | 7107 | 12823 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 500 | 2771 | 5.11 | 48.7 | 138 | 177978 | 320362 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 64 | 100 | 18076 | 178.88 | 280.6 | 126 | 284721 | 512275 | 

## RL-style: parallel workers (8 sections, 200 episodes/worker)

| engine | workers | wall ms | episodes/s | total RSS MiB |
|---|---|---|---|---|
| devspy@eb23a82 | 1 | 1859 | 108 | 14 |
| devspy@eb23a82 | 4 | 1966 | 407 | 56 |
| devspy@eb23a82 | 8 | 2011 | 795 | 112 |
| devspy@eb23a82 | 16 | 3106 | 1030 | 223 |
| devspy[devspy-mypyc] | 1 | 1635 | 122 | 14 |
| devspy[devspy-mypyc] | 4 | 1709 | 468 | 57 |
| devspy[devspy-mypyc] | 8 | 1811 | 884 | 113 |
| devspy[devspy-mypyc] | 16 | 2824 | 1133 | 226 |
| devsjava | 1 | 1654 | 121 | 419 |
| devsjava | 4 | 2411 | 332 | 1683 |
| devsjava | 8 | 3907 | 409 | 3391 |
| devsjava | 16 | 7201 | 444 | 6930 |
| xdevs | 1 | 1612 | 124 | 24 |
| xdevs | 4 | 1638 | 488 | 95 |
| xdevs | 8 | 1790 | 894 | 190 |
| xdevs | 16 | 2843 | 1126 | 380 |
| pypdevs-minimal | 1 | 936 | 214 | 12 |
| pypdevs-minimal | 4 | 972 | 823 | 46 |
| pypdevs-minimal | 8 | 1044 | 1533 | 93 |
| pypdevs-minimal | 16 | 1661 | 1926 | 186 |
| adevs | 1 | 91 | 2209 | 4 |
| adevs | 4 | 93 | 8567 | 15 |
| adevs | 8 | 117 | 13712 | 30 |
| adevs | 16 | 177 | 18117 | 60 |
| cadmium | 1 | 39 | 5184 | 4 |
| cadmium | 4 | 41 | 19579 | 15 |
| cadmium | 8 | 49 | 32452 | 30 |
| cadmium | 16 | 86 | 37154 | 60 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 1 | 1280 | 156 | 143 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 4 | 1974 | 405 | 594 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 8 | 3087 | 518 | 1128 |
| devsjava[-XX:+UseSerialGC -Xmx128m] | 16 | 5924 | 540 | 2298 |
