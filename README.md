# Распространение информации в распределённых системах

Лабораторная работа: алгоритмы unicast, multicast, broadcast, gossip (push, pull), rumor mongering и anti-entropy на 100+ узлах.

- **Симулятор** (`lab sim`): до 400 узлов, виртуальное время, управляемые потери и отказы.
- **Docker** (`lab docker`): 110 контейнеров с UDP-обменом и HTTP-управлением.

Отчёт: [`docs/report.pdf`](docs/report.pdf) (для печати) и [`docs/report.docx`](docs/report.docx) (для Google Docs).

## Запуск

Требуется Go 1.24+, Python 3, Docker Desktop (для Docker-серии).

```
python3 -m pip install -r requirements.txt
make test     # тесты
make sim      # симуляция, CSV в results/ (около 10 с)
make figures  # рисунки в docs/img/
make docker   # 110 контейнеров, около 80 мин
make report   # docs/report.pdf и docs/report.docx
```

## Структура

```
cmd/node            агент узла
cmd/lab             координатор: sim, docker, clean
internal/engine     алгоритмы, топологии, метрики
internal/sim        симулятор
internal/agent      HTTP/UDP-агент узла
internal/dockerlab  запуск контейнеров и прогоны
scripts/            рисунки и сборка отчёта
results/            CSV результатов
docs/               отчёт (report.md, report.pdf, report.docx), рисунки
```
