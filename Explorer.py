import os
import sys
import time
import shutil
import subprocess
import traceback
import datetime
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeView,
    QMessageBox,
    QMenu,
    QInputDialog,
    QAbstractItemView,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QHBoxLayout,
    QPushButton
)
from PyQt6.QtGui import QShortcut, QKeySequence, QFileSystemModel
from PyQt6.QtCore import QDir, QSortFilterProxyModel, Qt, QTimer
ROOT = os.path.expanduser("~") + os.sep + "Shared - Client"
def parse_events():
    path = os.path.join(ROOT, ".etc", "events")
    if not os.path.exists(path):return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(" ~~~ ")
            event = parts[0]
            path1 = os.path.join(ROOT,parts[1]) if len(parts) > 1 else ''
            path2 = os.path.join(ROOT,parts[2]) if len(parts) > 2 else ''
            undo = int(parts[-2])
            ts = parts[-1]
            if path2 and not path2.replace('.', '').isdigit():key = (event, path1, path2)
            else:key = (event, path1)
            out.append({"key": key,"event": event,"path1": path1,"path2": path2,"undo": undo,"ts": ts})
    return out
def get_next_undo_event():
    events = parse_events()
    state = {}
    for e in events:state.setdefault(e["key"], 0);state[e["key"]] += e["undo"]
    for e in reversed(events):
        if e["undo"] != 0:continue
        if state.get(e["key"], 0) == 0:return e
    return None
def get_next_redo_event():
    events = parse_events()
    state = {}
    for e in events:
        state.setdefault(e["key"], 0);state[e["key"]] += e["undo"]
    for e in reversed(events):
        if state.get(e["key"], 0) == -1:return e
    return None
def log_event(event,path1,path2='',undo=0):
    os.makedirs(os.path.join(ROOT, ".etc"), exist_ok=True)
    path1=os.path.relpath(path1,ROOT)
    if path2:path2=os.path.relpath(path2,ROOT)
    line=[event,path1,path2,str(undo),str(time.time())]
    if '' in line:line.remove('')
    with open(os.path.join(ROOT, ".etc", 'events'), "a", encoding="utf-8") as f:f.write(" ~~~ ".join(line) + "\n")
def is_inside_root(path: str) -> bool:return os.path.abspath(path).startswith(os.path.abspath(ROOT))
class HiddenFilter(QSortFilterProxyModel):
    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        path = self.sourceModel().filePath(index)
        if ".etc" in path.split(os.sep):return False
        return True
class Explorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FTP Explorer")
        self.resize(1000, 650)
        if not os.path.exists(ROOT):os.makedirs(ROOT, exist_ok=True)
        self.model = QFileSystemModel()
        self.model.setRootPath(ROOT)
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.proxy = HiddenFilter()
        self.proxy.setSourceModel(self.model)
        self.view = QTreeView()
        self.view.setModel(self.proxy)
        root_index = self.model.index(ROOT)
        self.view.setRootIndex(self.proxy.mapFromSource(root_index))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.open_menu)
        self.view.doubleClicked.connect(self.open_item)
        self.view.setColumnWidth(0, 300)
        self.view.setColumnWidth(1, 100)
        self.view.setColumnWidth(2, 100)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.main_tab = QWidget()
        self.main_layout = QVBoxLayout(self.main_tab)
        self.main_toolbar = QWidget()
        self.main_toolbar_layout = QHBoxLayout(self.main_toolbar)
        self.main_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.main_toolbar_layout.setSpacing(5)
        self.btn_new_folder = self.make_btn("New Folder", lambda: self.new_folder(self.view.currentIndex()))
        self.btn_new_file   = self.make_btn("New File", lambda: self.new_file(self.view.currentIndex()))
        self.btn_delete     = self.make_btn("Delete", self.delete_item)
        self.btn_rename     = self.make_btn("Rename", lambda: self.rename_item(self.view.currentIndex()))
        self.btn_copy       = self.make_btn("Copy", self.copy_item)
        self.btn_cut        = self.make_btn("Cut", self.cut_item)
        self.btn_paste      = self.make_btn("Paste", self.paste_item)
        self.btn_undo       = self.make_btn("Undo", self.cut_item)
        self.btn_redo       = self.make_btn("Redo", self.paste_item)
        for btn in [
            self.btn_new_folder,
            self.btn_new_file,
            self.btn_delete,
            self.btn_rename,
            self.btn_copy,
            self.btn_cut,
            self.btn_paste,
            self.btn_undo,
            self.btn_redo
        ]:
            self.main_toolbar_layout.addWidget(btn)
        self.main_layout.addWidget(self.main_toolbar)
        self.main_layout.addWidget(self.view)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.main_tab, "Main")
        self.trash_tab = QWidget()
        self.trash_layout = QVBoxLayout(self.trash_tab)
        self.trash_table = QTableWidget()
        self.trash_table.setColumnCount(4)
        self.trash_table.setHorizontalHeaderLabels(["Filename","Original Path","Date Deleted","Trash Path"])
        self.trash_table.setColumnHidden(3, True)
        self.trash_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trash_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trash_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trash_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.trash_table.customContextMenuRequested.connect(self.open_trash_menu)
        self.trash_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trash_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.trash_table.installEventFilter(self)
        self.trash_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabs.currentChanged.connect(self.on_tab_change)
        self.tabs.addTab(self.trash_tab, "Trash")
        self.setCentralWidget(self.tabs)
        self.view.installEventFilter(self)
        self.trash_toolbar = QWidget()
        self.trash_toolbar_layout = QHBoxLayout(self.trash_toolbar)
        self.trash_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.trash_toolbar_layout.setSpacing(5)
        self.btn_empty_trash = self.make_btn("Empty Trash", self.empty_trash)
        self.btn_delete_perm  = self.make_btn("Delete Permanently", self.delete_permanently)
        self.btn_restore      = self.make_btn("Restore", self.restore_selected)
        self.btn_restore_all  = self.make_btn("Restore All", self.restore_all)
        for btn in [
            self.btn_empty_trash,
            self.btn_delete_perm,
            self.btn_restore,
            self.btn_restore_all
        ]:
            self.trash_toolbar_layout.addWidget(btn)
        self.trash_layout.addWidget(self.trash_toolbar)
        self.trash_layout.addWidget(self.trash_table)
        self.clipboard = None
        self.setup_shortcuts()
    def make_btn(self, text, slot):
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        return btn
    def get_path(self, proxy_index):
        source = self.proxy.mapToSource(proxy_index)
        return self.model.filePath(source)
    def get_selected_paths(self):
        indexes = self.view.selectionModel().selectedRows()
        paths = []
        for index in indexes:
            source_index = self.proxy.mapToSource(index)
            path = self.model.filePath(source_index)
            if path:paths.append(path)
        return paths
    def get_selected_trash_rows(self):
        return sorted(set(index.row() for index in self.trash_table.selectedIndexes()))
    def open_item(self, index):
        path = self.get_path(index)
        if os.path.isdir(path):return
        if sys.platform.startswith("win"):os.startfile(path)
        else:subprocess.run(f'xdg-open "{path}"',shell=True)
    def open_menu(self, pos):
        index = self.view.indexAt(pos)
        menu = QMenu()
        if index.isValid():
            menu.addAction("Open", lambda: self.open_item(index))
            menu.addAction("Rename", lambda: self.rename_item(index))
            menu.addAction("Delete (Trash)", lambda: self.delete_item(index))
            menu.addSeparator()
            menu.addAction("Copy", lambda: self.copy_item())
            menu.addAction("Cut", lambda: self.cut_item())
            menu.addAction("Paste", lambda: self.paste_item())
        menu.addSeparator()
        menu.addAction("New Folder", lambda: self.new_folder(index))
        menu.exec(self.view.viewport().mapToGlobal(pos))
    def open_trash_menu(self, pos):
        if not self.trash_table.selectedIndexes():return
        menu = QMenu(self)
        restore_action = menu.addAction("Restore")
        delete_action = menu.addAction("Delete permanently")
        action = menu.exec(self.trash_table.mapToGlobal(pos))
        if action == restore_action:self.restore_selected()
        elif action == delete_action:self.delete_permanently()
    def delete_permanently(self):
        rows = self.get_selected_trash_rows()
        if not rows:return
        reply = QMessageBox.question(
            self,
            "Confirm delete",
            f"Permanently delete {len(rows)} item(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:return
        for row in rows:
            trash_path = self.trash_table.item(row, 3).text()
            try:
                if os.path.isdir(trash_path):shutil.rmtree(trash_path)
                else:os.remove(trash_path)
                log_event("delete_permanent", trash_path, "", 0)
            except Exception:
                pass
        self.refresh_trash()
    def copy_item(self):
        paths = self.get_selected_paths()
        if not paths:return
        self.clipboard = {"paths": paths, "mode": 1}
    def cut_item(self):
        paths = self.get_selected_paths()
        if not paths:return
        self.clipboard = {"paths": paths, "mode": 2}
    def paste_item(self):
        if not self.clipboard or not self.clipboard["paths"]: return
        mode = self.clipboard["mode"]
        sources = self.clipboard["paths"]
        index = self.view.currentIndex()
        if index.isValid():
            selected_path = self.get_path(index)
            if os.path.isdir(selected_path):dest_dir = selected_path
            else:dest_dir = os.path.dirname(selected_path)
        else:dest_dir = self.get_path(self.view.rootIndex())
        if not os.path.isdir(dest_dir):dest_dir = os.path.dirname(dest_dir)
        if not is_inside_root(dest_dir):return
        new_paths = []
        for src in sources:
            name = os.path.basename(src)
            dst = os.path.join(dest_dir, name)
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(dst):
                dst = os.path.join(dest_dir, f"{base} ({i}){ext}")
                i += 1
            try:
                if mode == 1:
                    if os.path.isdir(src): shutil.copytree(src, dst)
                    else: shutil.copy2(src, dst)
                    log_event("copy", src, dst)
                elif mode == 2:
                    shutil.move(src, dst)
                    log_event("move", src, dst)
                new_paths.append(dst)
            except Exception as e:
                traceback.print_exception(e)
                QMessageBox.critical(self, "Error", str(e))
        if mode==2:self.clipboard = {"paths": new_paths, "mode": 1}
    def undo_event(e):
        event = e["event"]
        p1 = e["path1"]
        p2 = e.get("path2", "")
        try:
            if event == "create":
                if os.path.exists(p1):
                    if os.path.isdir(p1):shutil.rmtree(p1)
                    else:os.remove(p1)
            elif event == "delete":
                if os.path.exists(p2):
                    os.makedirs(os.path.dirname(p1), exist_ok=True)
                    shutil.move(p2, p1)
            elif event == "move":
                if os.path.exists(p2):shutil.move(p2, p1)
            elif event == "copy":
                if os.path.exists(p2):
                    if os.path.isdir(p2):shutil.rmtree(p2)
                    else:os.remove(p2)
        except Exception:pass
        log_event(event, p1, p2, undo=-1)
    def redo(self):
        e=get_next_redo_event()
        if not e:return
        event = e["event"]
        p1 = e["path1"]
        p2 = e.get("path2", "")
        try:
            if event == "create":os.makedirs(p1, exist_ok=True)
            elif event == "delete":
                if os.path.exists(p1):shutil.move(p1, p2)
            elif event == "move":
                if os.path.exists(p1):shutil.move(p1, p2)
            elif event == "copy":
                if os.path.exists(p1):
                    if os.path.isdir(p1):shutil.copytree(p1, p2)
                    else:shutil.copy2(p1, p2)
        except Exception:pass
        log_event(event, p1, p2, undo=1)
    def undo(self):
        e = get_next_undo_event()
        if not e:return
        event = e["event"]
        p1 = e["path1"]
        p2 = e.get("path2", "")
        try:
            if event == "create":
                if os.path.exists(p1):
                    if os.path.isdir(p1):shutil.rmtree(p1)
                    else:os.remove(p1)
            elif event == "delete":
                if os.path.exists(p2):
                    os.makedirs(os.path.dirname(p1), exist_ok=True)
                    shutil.move(p2, p1)
            elif event == "move":
                if os.path.exists(p2):shutil.move(p2, p1)
            elif event == "copy":
                if os.path.exists(p2):
                    if os.path.isdir(p2):shutil.rmtree(p2)
                    else:os.remove(p2)
        except Exception:pass
        log_event(event, p1, p2, undo=-1)
    def delete_item(self):
        if self.tabs.currentIndex()==1:return self.delete_permanently()
        paths = self.get_selected_paths()
        if not paths:return
        trash_dir = os.path.join(ROOT, os.path.join(".etc","Trash"))
        os.makedirs(trash_dir, exist_ok=True)
        for src in paths:
            try:
                name = os.path.basename(src)
                dst = os.path.join(trash_dir, name)
                base, ext = os.path.splitext(name)
                i = 1
                while os.path.exists(dst):
                    dst = os.path.join(trash_dir, f"{base} ({i}){ext}")
                    i += 1
                shutil.move(src, dst)
                log_event("delete", src, dst, 0)
            except Exception as e:
                print(e)
        self.view.viewport().update()
    def rename_item(self, index):
        old = self.get_path(index)
        if not is_inside_root(old):return
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:",text=os.path.basename(old))
        if not ok or not new_name:return
        new_path = os.path.join(os.path.dirname(old), new_name)
        try:os.rename(old, new_path);log_event("move", old, new_path)
        except Exception as e:
            traceback.print_exception(e)
            QMessageBox.critical(self, "Error", str(e))
    def copy_file(self, src, dst):
        try:
            shutil.copy2(src, dst)
            log_event("copy", src, dst)
        except Exception as e:
            traceback.print_exception(e)
            QMessageBox.critical(self, "Error", str(e))
    def new_folder(self, index):
        path = self.get_path(index) if index.isValid() else ROOT
        if not is_inside_root(path):return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name:return
        full = os.path.join(path, name)
        try:os.makedirs(full, exist_ok=True);log_event("create", full)
        except Exception as e:
            traceback.print_exception(e)
            QMessageBox.critical(self, "Error", str(e))
    def new_file(self, index):
        path = self.get_path(index) if index.isValid() else ROOT
        path=os.path.dirname(path)
        if not is_inside_root(path):return
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if not ok or not name:return
        full = os.path.join(path, name)
        try:
            with open(full,'x') as f:f.close()
            log_event("create", full)
        except Exception as e:
            traceback.print_exception(e)
            QMessageBox.critical(self, "Error", str(e))
    def refresh_trash(self):
        self.trash_table.setRowCount(0)
        log_path = os.path.join(ROOT, ".etc", "events")
        if not os.path.exists(log_path):return
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" ~~~ ")
                if parts[0] != "delete":continue
                src = os.path.join(ROOT,parts[1])
                dst = os.path.join(ROOT,parts[2])
                ts = float(parts[-1])
                if not os.path.exists(dst):continue
                row = self.trash_table.rowCount()
                self.trash_table.insertRow(row)
                self.trash_table.setItem(row, 0, QTableWidgetItem(os.path.basename(src)))
                self.trash_table.setItem(row, 1, QTableWidgetItem(src))
                self.trash_table.setItem(row, 2, QTableWidgetItem(datetime.datetime.fromtimestamp(ts).strftime('%d %b %Y %H:%M')))
                self.trash_table.setItem(row, 3, QTableWidgetItem(dst))
    def get_all_trash_indexes(self):
        return list(range(self.trash_table.rowCount()))
    def empty_trash(self):
        for filename in os.listdir(os.path.join(ROOT,".etc","Trash")):
            path = os.path.join(os.path.join(ROOT,".etc","Trash"), filename)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as e:
                print("Failed to delete:", path, e)
        self.refresh_trash()
    def restore_all(self):
        self.restore_selected(self.get_all_trash_indexes())

    def restore_selected(self,rows=None):
        if not rows:
            rows = self.get_selected_trash_rows()
        print(rows)
        if not rows:return
        for row in rows:
            trash_path = self.trash_table.item(row, 3).text()
            original_path = self.trash_table.item(row, 1).text()
            if not os.path.exists(trash_path):continue
            name = os.path.basename(original_path)
            restore_path = original_path
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(restore_path):
                restore_path = os.path.join(
                    os.path.dirname(original_path),
                    f"{base} ({i}){ext}"
                )
                i += 1
            try:
                shutil.move(trash_path, restore_path)
                log_event("restore", trash_path, restore_path, 0)
            except Exception:
                pass
        self.refresh_trash()
    def on_tab_change(self, index):
        if index == 0:
            self.view.setFocus()
            self.refresh()
        elif index == 1:
            self.trash_table.setFocus()
            self.refresh_trash()
    def setup_shortcuts(self):
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(lambda: self.new_folder(self.view.currentIndex()))
        QShortcut(QKeySequence("F2"), self).activated.connect(lambda: self.rename_item(self.view.currentIndex()))
        QShortcut(QKeySequence("Delete"), self).activated.connect(self.delete_item)
        QShortcut(QKeySequence("Return"), self).activated.connect(lambda: self.open_item(self.view.currentIndex()))
        QShortcut(QKeySequence("Enter"), self).activated.connect(lambda: self.open_item(self.view.currentIndex()))
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self.go_up)
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(self.copy_item)
        QShortcut(QKeySequence("Ctrl+X"), self).activated.connect(self.cut_item)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self.paste_item)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self.redo)
    def go_up(self):
        index = self.view.rootIndex()
        path = self.get_path(index)
        parent = os.path.dirname(path)
        if not is_inside_root(parent):return
        self.view.setRootIndex(self.proxy.mapFromSource(self.model.index(parent)))
    def refresh(self):self.model.setRootPath(ROOT)
def MAIN():
    print(1)
    app = QApplication(sys.argv)
    print(2)
    w = Explorer()
    print(3)
    w.show()
    print(4)
    app.exec()
if __name__=='__main__':MAIN()