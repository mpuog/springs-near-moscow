"""
микро-редактор описаний точек файлов gpx

Пример файла - один элемент <metadata> и много элементов <wpt>

<metadata>
 <time>2023-06-01T08:40:16Z</time>
 <bounds minlat="54.953477" minlon="37.769822" maxlat="54.955547" maxlon="37.820205"/>
</metadata>
<wpt lat="54.9555470" lon="37.8181450">
 <time>2023-05-23T00:00:00.000Z</time>
 <name>WPT1</name>
 <cmt>ЛАПИНО CMT</cmt>
 <desc>ЛАПИНО CMT</desc>
 <sym>Airport</sym>
</wpt>

Для упрощения НЕ трогаем широту и долготу, удаляем <desc>.
Автоматически правим <metadata><time>, <metadata><bounds> и <wpt><time>

Чтобы добавить новую точку достаточно в любом текстовом редакторе добавить
"кусочек" <wpt> .. </wpt> из другого gpx-файла в конец, но перед закрывающим
</gpx> Уникальность имен точек "на совести" добавляющего

После работы с файлом в OZI Explorer через Import/Export GPX надо запустить
скрипт и сохранить файл.

В файле читает в таблицу все описания точек (элемент <wpt> .. </wpt>).
Внутри читаются и остаются после обработки только
    <cmt>CMT ONLY</cmt>
    <name>2</name>
    <sym>Airport</sym>

координаты в элементе <wpt>, <name> и <sym> НЕ РЕДАКТИРУЮТСЯ (пока?)

описание приводится в соответствие с "возможностями" OZI Explorer
(обрезка до 100 знаков, удаляются запятые и русская С).

todo обработка символов (<sym>), (полу?)автоматическая

todo заменить ли поиск по имени на поиск по координатам
"""

import re
import datetime
import sys
from collections import namedtuple
from decimal import Decimal
from tkinter import *
from tkinter import ttk, filedialog
from tkinter.messagebox import askyesnocancel, showinfo, showerror

import lxml.etree as etree


# Литералы из gpx-файлов
def named_list(string, name="NAMED_LIST"):
    return namedtuple(name, string)(*string.split())


G = named_list(
    'values '
    'metadata time bounds maxlat minlat maxlon minlon '
    'wpt name lat lon cmt desc sym',
    'string_constants')

HELP = """    Минималистический редактор-корректор файла gpx.

    Исправлять (пока?) можно только комментарий.
    Вход в редактирование комментария дабл-клик
на нужной строчке.

В процессе редактирования поля доступны команды:
    Ctrl-A - выделить все;
    Escape, дабл-клик на другой строчке
           - выход из поля без сохранения изменений; 
    Return - сохранить изменения. В процессе 
             сохранения возможны проблемы, 
             если строчка "не вписывается" 
             в допустимый в OZI Explorer размер комментария.
"""

# Время для записи в элемент time, если что-то в данных изменено.
# Переходом к гринвичу, поскольку в OZI используется гринвич.
CURR_TIME_STAMP = datetime.datetime.now(
    datetime.timezone.utc).isoformat(timespec='milliseconds')[:23] + 'Z'
OZI_MAX_COMMENT_CHARS = 100
OZI_MAX_NAME_CHARS = 100

# "Хвост" элемента в описании точки, для "хорошего" форматирования.
typicalTail = '\n'


def ozi_str(s: str) -> str:
    """Корректор строк для совместимости с OZI Explorer.

    Убираем пробелы при знаках препинания, двойные пробелы,
    заменяем запятые и букву С русскую
    """

    s = re.sub(r'\s+', ' ', s)
    s = s.replace('С', 'C')
    s = s.replace(',', ';')
    s = s.replace(';;', ';')
    if len(s) > OZI_MAX_COMMENT_CHARS:
        s = re.sub(r'(\W)\s+', r'\1', s)
        s = re.sub(r'\s+(\W)', r'\1', s)
    return s


class TableGPX(ttk.Treeview):
    """ Табличка для отображения списка точек файла gpx """

    def __init__(self, gpx, *args, **kwargs):
        super().__init__(columns=("name", "lat_lon", "cmt"), show="headings")
        self.bind("<Double-1>", lambda event: self.onDoubleClick(event))

        # определяем заголовки
        self.heading("name", text="Имя(латиница!)", anchor=W)
        self.heading("lat_lon", text="Координаты", anchor=W)
        self.heading("cmt", text="Комментарий до 100 символов", anchor=W)
        self.column("#1", stretch=NO, width=120)
        self.column("#2", stretch=NO, width=200)
        self.column("#3", stretch=NO, width=640)

        self.gpx = gpx
        self.table_filling()

    def table_filling(self):
        """ Заполняем табличку """
        global typicalTail
        for wptXml in self.gpx.findall('.//wpt', self.gpx.nsmap):
            typicalTail = wptXml[0].tail  # каждый раз, "не жалко" :)
            nameXml = wptXml.find(G.name, self.gpx.nsmap)
            nameStr = '' if nameXml is None else nameXml.text
            cmtXml = wptXml.find(G.cmt, self.gpx.nsmap)
            cmtStr = '' if cmtXml is None else cmtXml.text
            # desc получаем и удаляем
            descXml = wptXml.find(G.desc, self.gpx.nsmap)
            if descXml is not None:
                # Если в cmt пусто, возьмем туда текст из desc
                if not cmtStr and descXml.text:
                    cmtStr = descXml.text
                    cmtXml = etree.Element(
                        f'{{{self.gpx.nsmap[None]}}}' + G.cmt)
                    cmtXml.text = descXml.text
                    cmtXml.tail = typicalTail
                    wptXml.insert(-1, cmtXml)

                wptXml.remove(descXml)
            self.insert("", END, values=(
                nameStr, f"{wptXml.get(G.lat)}, {wptXml.get(G.lon)}", cmtStr))

    def onDoubleClick(self, event):
        """ Executed, when a row is double-clicked. Opens
        read-only EntryPopup above the item's column, so it is possible
        to select text

        NB! Код избыточен, пытаемся отследить редактирование нескольких полей
        """

        # close previous popups
        try:  # in case there was no previous popup
            self.entryPopup.destroy()
        except AttributeError:
            pass

        # what row and column was clicked on
        rowid = self.identify_row(event.y)
        column = self.identify_column(event.x)
        # Редактировать (пока?) разрешено только описание
        column = '#3'

        # handle exception when header is double click
        if not rowid:
            return

        # get column position info
        x, y, width, height = self.bbox(rowid, column)

        # y-axis offset
        pady = height // 2

        # place Entry popup properly
        text = self.item(rowid, G.values)[int(column[1:]) - 1]
        self.entryPopup = EntryPopup(
            self, rowid, int(column[1:]) - 1, text, self.gpx)
        self.entryPopup.place(x=x, y=y + pady, width=width, height=height, anchor='w')
        t2 = self.item(rowid, G.values)[int(column[1:]) - 1]
        t3 = self.item(rowid, G.values)[int(column[1:]) - 1]


class EntryPopup(ttk.Entry):
    """Открывающееся поле для ввода с записью в XML gpx, при изменении"""

    def __init__(self, parent, iid, column, text, gpx, **kw):
        ttk.Style().configure('pad.TEntry', padding='1 1 1 1')
        super().__init__(parent, style='pad.TEntry', **kw)
        self.tv = parent
        self.iid = iid
        self.column = column
        self.textInput = text
        self.gpx = gpx

        self.insert(0, text)
        # self['state'] = 'readonly'
        # self['readonlybackground'] = 'white'
        # self['selectbackground'] = '#1BA1E2'
        self['exportselection'] = False

        self.focus_force()
        self.select_all()
        self.bind("<Return>", self.on_return)
        self.bind("<Control-a>", self.select_all)
        self.bind("<Escape>", lambda *ignore: self.destroy())

    def on_return(self, event):
        """ Изменить значение """
        rowid = self.tv.focus()
        # Проверяем, изменилось ли значение
        if (text := self.get()) != self.textInput:
            textOzi = ozi_str(text)
            if len(textOzi) > OZI_MAX_COMMENT_CHARS:
                showerror('Превышена длина комментария',
                          f'Из строки необходимо убрать ещё '
                          f'{len(textOzi) - OZI_MAX_COMMENT_CHARS}'
                          f' значащих символов.')
                return
            # Записываем новое значение в таблицу и XML
            nameStr = self.tv.item(self.iid, G.values)[0]
            nameXml = self.gpx.find(f"wpt/name[.='{nameStr}']",
                                    namespaces=self.gpx.nsmap)
            if nameXml is None:
                showerror('Internal error',
                          'В данных нет точки по имени в таблице,'
                          ' изменения не сохранятся!')
            else:
                wptXml = nameXml.getparent()
                timeXml = wptXml.find(G.time, namespaces=self.gpx.nsmap)
                if timeXml is None:
                    # timeXml = etree.SubElement(wptXml, f'{{{wptXml.nsmap[None]}}}time')  #, nsmap=wptXml.nsmap)
                    timeXml = etree.Element(
                        f'{{{wptXml.nsmap[None]}}}' + G.time)
                    timeXml.text = CURR_TIME_STAMP
                    timeXml.tail = typicalTail
                    wptXml.insert(0, timeXml)
                cmtXml = wptXml.find(G.cmt, namespaces=self.gpx.nsmap)
                if cmtXml is None:
                    cmtXml = etree.Element(
                        f'{{{wptXml.nsmap[None]}}}' + G.cmt)
                    cmtXml.tail = typicalTail
                    wptXml.insert(-1, cmtXml)
                cmtXml.text = text
                vals = self.tv.item(rowid, G.values)
                vals = list(vals)
                vals[self.column] = text
                self.tv.item(rowid, values=vals)
        self.destroy()

    def select_all(self, *ignore):
        """ Set selection on the whole text """
        self.selection_range(0, 'end')
        # returns 'break' to interrupt default key-bindings
        return 'break'


def help_dialog(event):
    # TODO переделать на немодальный диалог
    showinfo(title="Информация", message=HELP)


def save(gpx, gpxStrin, filePath):
    """ Сохранение данных, перед сохранением проверяем,
    изменилось ли что-нибудь """

    if etree.tounicode(gpx) == gpxStrin:
        return  # Ничего не изменилось
    # пробег по всем узлам, получение массивов широты, долготы, времени
    latitudes = []
    longitudes = []
    times = [CURR_TIME_STAMP]  # если что-то менялось, поставим текущее время
    for wptXml in gpx.findall(G.wpt, gpx.nsmap):
        latitudes.append(round(Decimal(wptXml.get(G.lat)), 6))
        longitudes.append(round(Decimal(wptXml.get(G.lon)), 6))
        if (timeXml := wptXml.find(G.time, gpx.nsmap)) is not None:
            times.append(timeXml.text)

    # корректировка <metadata>
    metadata = gpx.find(G.metadata, gpx.nsmap)
    # NB! Точки не добавляются в программе, но могли быть добавлены "внешним"
    # редактором, поэтому проверяем максимальные широту-долготу всегда
    minLat, maxLat = min(latitudes), max(latitudes)
    minLon, maxLon = min(longitudes), max(longitudes)
    maxTime = max(times)
    bounds = metadata.find(G.bounds, gpx.nsmap)
    time = metadata.find(G.time, gpx.nsmap)
    bounds.set(G.minlat, f'{minLat:.6f}')
    bounds.set(G.maxlat, f'{maxLat:.6f}')
    bounds.set(G.minlon, f'{minLon:.6f}')
    bounds.set(G.maxlon, f'{maxLon:.6f}')
    time.text = maxTime

    # Собственно запись. Заголовок вручную сделан,
    # чтобы не отличался от формируемого OZI Explorer
    # outFile = 'test_out.gpx'
    outFile = filePath
    open(outFile, 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
        etree.tounicode(gpx, pretty_print=True))


def deactivate(root, gpx, gpxStrIn, filePath):
    """ Проверка на выходе, пока не реализована... """
    askyesnocancel()
    # todo сохранение или продолжение
    root.destroy()


def main():
    """ main """

    # create root window
    root = Tk()
    root.title("Микро-редактор файла GPX с точками родников")
    root.geometry("990x300")
    root.rowconfigure(index=0, weight=1)
    root.columnconfigure(index=0, weight=1)

    # входной файл либо из командной строки, либо читаем в диалоге
    if not sys.argv[1:]:
        # todo диалог чтения файла, если не передано имя (точнее, ещё если передано неправильное)
        filePath = filedialog.askopenfilename(
            title="Выбор файла", defaultextension='gpx', initialdir='.')
        if not filePath:
            root.destroy()
    else:
        filePath = sys.argv[1]

    with open(filePath, 'rb') as inpFile:
        gpx = etree.fromstring(inpFile.read())
    # запоминаем исходное состояние в виде строки,
    # чтобы проверить, появились ли изменения
    gpxStrIn = etree.tounicode(gpx)

    # Создаем ьабличку (класс производный от treeview)
    table = TableGPX(gpx)
    table.grid(row=0, column=0, sticky="nsew")

    # добавляем вертикальную прокрутку
    scrollbar = ttk.Scrollbar(orient=VERTICAL, command=table.yview)
    table.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns")

    # В нижней части окна управляющие кнопки
    bottomFrame = Frame()
    bottomFrame.grid(row=1, column=0, sticky="")
    cancelButton = Button(bottomFrame, text="Cancel", command=root.destroy)
    cancelButton.pack(side=LEFT)
    saveButton = Button(bottomFrame, text="Save",
                        command=lambda: save(gpx, gpxStrIn, filePath))
    saveButton.pack(side=LEFT)
    file = Label(bottomFrame, text=filePath)
    file.pack(side=LEFT)

    # Общие события
    root.bind('<F1>', help_dialog)
    # Проверка на выходе, пока просто отключаем, да она и не реализована...
    # root.protocol("WM_DELETE_WINDOW", lambda: deactivate(root, gpx, gpxStrIn, filePath))

    root.mainloop()


if __name__ == '__main__':
    main()
