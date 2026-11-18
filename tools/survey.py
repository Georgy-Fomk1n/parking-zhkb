#!/usr/bin/env python3
"""Пересчёт итогов опроса жителей ЖК «На Базовской» для index.html.

Запуск (из корня репозитория):

    python3 tools/survey.py путь/к/выгрузке.csv            # только показать цифры
    python3 tools/survey.py путь/к/выгрузке.csv index.html # ещё и пересобрать таблицу по корпусам

Что делает скрипт:
  * печатает цифры для карточек «Что говорят соседи», карточки «мест к аренде»
    и процентов опасений в FAQ — их нужно вручную вписать в index.html;
  * с вторым аргументом заменяет строки таблицы «Ответы по корпусам»
    (всё между <tbody> и </tbody>) прямо в index.html.

Методика (совпадает с опубликованными цифрами):
  * Итоги и карточки: только жители ЖК (ответ «Корпус N») и только первые ответы
    от квартиры (на вопрос о повторе ответили «Нет, отвечаю впервые»).
  * Таблица по корпусам: все анкеты жителей ЖК, включая повторные.
  * Погрешность: 95% интервал для доли 50% с поправкой на конечную совокупность
    (число квартир корпуса).
  * Надёжность: «Надёжно» — охват от 15% и погрешность до ±15 п.п.;
    «Ориентир» — охват от 10%; «Мало ответов» — охват меньше 10%.
  * Мест к аренде: «1 место» = 1, «2 места» = 2, «3 места и более» = 3.
  * Медиана цены: только ответы, записанные одним числом (5000, 10 000);
    диапазоны и текст («До 5000», «3-5 тыс») не учитываются.

Столбцы ищутся по тексту заголовков из выгрузки Яндекс Форм (см. HEADERS).
Если в форме переформулируют вопросы, скрипт остановится и назовёт столбец,
который не нашёл; тогда поправьте HEADERS.

Выгрузку с ответами в репозиторий не кладите: в ней есть комментарии жителей.
"""
import csv
import math
import re
import statistics as st
import sys

TOTAL_APARTMENTS = 2537

# Квартир в каждом корпусе (по разрешениям на ввод в эксплуатацию).
APARTMENTS = {'1': 288, '2': 192, '3': 192, '4': 204, '5': 288, '6': 288,
              '7': 192, '8': 192, '9': 192, '10': 128, '11': 128, '15': 253}

# Столбцы ищутся по началу заголовка, а не по номеру: если респондент заполнит
# повторяющиеся блоки (по одному на каждую машину), форма добавляет в выгрузку
# новые столбцы и номера остальных сдвигаются. Для повторяющихся вопросов
# берём первый блок — «[1]».
HEADERS = {
    'building': 'В каком корпусе ЖК «На Базовской» вы проживаете?',
    'repeat': 'Вы или кто-то из вашей семьи уже отвечали на этот опрос?',
    'permanent': 'Есть ли у вас постоянное парковочное место',
    'difficulty': 'Как часто вы сталкиваетесь с трудностями при парковке',
    'ambulance': 'С какими ситуациями, связанными с парковкой в ЖК, вам приходилось лично '
                 'сталкиваться или которые вы наблюдали? / Затруднён проезд скорой помощи',
    'not_offered': 'Что изменилось у вашего дома после установки знаков «Остановка запрещена»? '
                   '/ Жителям не предложили',
    'not_warned': 'Что изменилось у вашего дома после установки знаков «Остановка запрещена»? '
                  '/ Жителей заранее не предупредили',
    'support': 'Как вы относитесь к инициативе строительства многоуровневого паркинга',
    'rent': 'Рассматривали бы вы аренду машино-места',
    'spots': 'Сколько машино-мест ваша семья потенциально готова арендовать?',
    'fear_price': 'Какие опасения у вас вызывает строительство нового паркинга? / Высокая цена аренды',
    'fear_outsiders': 'Какие опасения у вас вызывает строительство нового паркинга? / Места достанутся не жителям',
    'fear_doubt': 'Какие опасения у вас вызывает строительство нового паркинга? / Сомневаюсь',
    'price': 'Какую ежемесячную стоимость аренды одного машино-места вы считали бы приемлемой? [1]',
    'appeal': ('Готовы ли вы поддержать обращение в Департамент транспорта Москвы? / Готов(а) отправить',
               'Готовы ли вы поддержать обращение в Департамент транспорта Москвы? / Уже отправил',
               'Готовы ли вы поддержать обращение в Департамент транспорта Москвы? / Готов(а) подписать'),
}
COL = {}


def find_columns(header):
    def one(prefix):
        hits = [i for i, h in enumerate(header) if h.strip().startswith(prefix)]
        if len(hits) != 1:
            sys.exit(f'Столбец «{prefix}» найден {len(hits)} раз, ожидался 1. '
                     f'Сверьте HEADERS с заголовком CSV.')
        return hits[0]
    for key, prefix in HEADERS.items():
        COL[key] = tuple(one(p) for p in prefix) if isinstance(prefix, tuple) else one(prefix)

LABELS = {'ok': 'Надёжно', 'mid': 'Ориентир', 'low': 'Мало ответов'}
SPOTS = {'1 место': 1, '2 места': 2, '3 места и более': 3}


def daily(x): return x[COL['difficulty']] == 'Ежедневно'
def no_place(x): return x[COL['permanent']].startswith('Нет, каждый')
def supports(x): return x[COL['support']] in ('Полностью поддерживаю', 'Скорее поддерживаю')
def would_rent(x): return x[COL['rent']].startswith(('Да', 'Скорее да'))
def marked(col): return lambda x: x[col] != ''


def share(cond, rows):
    return 100 * sum(1 for x in rows if cond(x)) / len(rows)


def spots(rows):
    return sum(SPOTS.get(x[COL['spots']], 0) for x in rows)


def median_price(rows):
    vals = []
    for x in rows:
        s = x[COL['price']].replace(' ', '').replace(' ', '')
        if re.fullmatch(r'\d+', s):
            vals.append(int(s))
    return st.median(vals) if vals else None


def fmt(v):
    """72.0 -> '72', 16.1 -> '16,1' — как в таблице на сайте."""
    return f'{v:.1f}'.rstrip('0').rstrip('.').replace('.', ',')


def rub(v):
    return f'{int(v):,}'.replace(',', ' ') if v is not None else '—'


def table_rows(residents):
    out = []
    for k, apts in APARTMENTS.items():
        b = [x for x in residents if x[COL['building']] == 'Корпус ' + k]
        m = len(b)
        if not m:
            print(f'! Корпус {k}: нет анкет, строка пропущена', file=sys.stderr)
            continue
        cov = 100 * m / apts
        moe = 196 * 0.5 / math.sqrt(m) * math.sqrt((apts - m) / (apts - 1))
        rel = 'ok' if cov >= 15 and moe <= 15 else ('mid' if cov >= 10 else 'low')
        cells = [apts, m, fmt(round(cov, 1)) + '%', '±' + fmt(round(moe, 1)),
                 f'<span class="rel">{LABELS[rel]}</span>']
        cells += [fmt(round(share(c, b), 1)) + '%' for c in (daily, no_place, supports, would_rent)]
        cells += [spots(b), rub(median_price(b))]
        out.append(f'          <tr class="{rel}"><th scope="row">{k}</th>'
                   + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        print(f'  корпус {k:>2}: {m:>3} анкет, охват {fmt(round(cov, 1))}%, {LABELS[rel]}')
    return out


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    with open(sys.argv[1], encoding='utf-8') as fh:
        header, *rows = list(csv.reader(fh))
    find_columns(header)
    residents = [x for x in rows if x[COL['building']].startswith('Корпус')]
    first = [x for x in residents if x[COL['repeat']].startswith('Нет')]

    print(f'Анкет всего: {len(rows)}, жителей ЖК: {len(residents)}, '
          f'квартир (без повторов): {len(first)} — '
          f'{fmt(round(100 * len(first) / TOTAL_APARTMENTS, 1))}% от {TOTAL_APARTMENTS}')
    print('\nКарточки «Что говорят соседи» (точное значение → на сайт):')
    for name, cond in [
        ('Трудности каждый день', daily),
        ('Нет постоянного места', no_place),
        ('Машины мешают скорой или пожарной', marked(COL['ambulance'])),
        ('Поддерживают паркинг', supports),
        ('Готовы арендовать', would_rent),
        ('Не предложили, где оставлять', marked(COL['not_offered'])),
        ('Не предупредили о знаках', marked(COL['not_warned'])),
        ('Готовы поддержать обращение', lambda x: any(x[i] for i in COL['appeal'])),
    ]:
        v = share(cond, first)
        print(f'  {name:<36} {v:6.2f} → {round(v)}%')
    print(f'\nМест к аренде: {spots(first)}')
    print(f'Медиана приемлемой цены: {rub(median_price(first))} ₽')
    print('\nОпасения (FAQ):')
    for name, col in [('Высокая цена', 'fear_price'), ('Места не жителям', 'fear_outsiders'),
                      ('Сомнения в реализации', 'fear_doubt')]:
        v = share(marked(COL[col]), first)
        print(f'  {name:<36} {v:6.2f} → {round(v)}%')

    print(f'\nТаблица по корпусам ({len(residents)} анкет):')
    rows_html = table_rows(residents)
    if len(sys.argv) == 3:
        path = sys.argv[2]
        with open(path, encoding='utf-8') as fh:
            page = fh.read()
        new, n = re.subn(r'(        <tbody>\n).*?(        </tbody>)',
                         lambda mm: mm.group(1) + '\n'.join(rows_html) + '\n' + mm.group(2),
                         page, count=1, flags=re.S)
        if not n:
            sys.exit(f'В {path} не найдена таблица <tbody>')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(new)
        print(f'\nТаблица в {path} обновлена. Карточки, FAQ и даты поправьте вручную.')


if __name__ == '__main__':
    main()
