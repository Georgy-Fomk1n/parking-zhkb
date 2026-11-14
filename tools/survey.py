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

Номера столбцов взяты из выгрузки Яндекс Форм (173 столбца). Если в форме
поменяют вопросы, сверьте номера в COL с заголовком CSV.

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

COL = {
    'building': 4,        # В каком корпусе вы проживаете?
    'repeat': 6,          # Вы или кто-то из семьи уже отвечали?
    'permanent': 22,      # Есть ли постоянное парковочное место?
    'difficulty': 23,     # Как часто трудности при парковке?
    'ambulance': 79,      # Затруднён проезд скорой или пожарной
    'not_offered': 90,    # Знаки: жителям не предложили, где оставлять машины
    'not_warned': 91,     # Знаки: жителей заранее не предупредили
    'support': 104,       # Отношение к многоуровневому паркингу
    'rent': 105,          # Рассматривали бы аренду?
    'spots': 106,         # Сколько мест готовы арендовать?
    'fear_price': 111,    # Опасение: высокая цена аренды
    'fear_outsiders': 112,  # Опасение: места достанутся не жителям ЖК
    'fear_doubt': 115,    # Опасение: проект не реализуют
    'price': 119,         # Приемлемая цена аренды, ₽ в месяц
    'appeal': (164, 165, 166),  # Готовы поддержать обращение (любой из вариантов)
}

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
        rows = list(csv.reader(fh))[1:]
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
