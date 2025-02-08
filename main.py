import time
import requests
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QThread
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QWidget, QVBoxLayout, QScrollBar
from loguru import logger
from qfluentwidgets import isDarkTheme

WIDGET_CODE = 'widget_yiyan.ui'
WIDGET_NAME = '每日一言 | LaoShui'
WIDGET_WIDTH = 360
API_URL = "https://api.codelife.cc/yiyan/info?lang=cn"

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/91.0.4472.124 Safari/537.36 Edge/91.0.864.64'
    )
}


class FetchThread(QThread):
    """网络请求线程"""
    fetch_finished = pyqtSignal(dict)  # 成功信号
    fetch_failed = pyqtSignal()  # 失败信号

    def __init__(self):
        super().__init__()
        self.max_retries = 3

    def run(self):
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                response = requests.get(API_URL, headers=HEADERS, proxies={'http': None, 'https': None})
                response.raise_for_status()
                data = response.json().get("data", {})
                if data:
                    self.fetch_finished.emit(data)
                    return
            except Exception as e:
                logger.error(f"请求失败: {e}")

            retry_count += 1
            time.sleep(2)

        self.fetch_failed.emit()


class SmoothScrollBar(QScrollBar):
    """平滑滚动条"""
    scrollFinished = pyqtSignal()

    def __init__(self, parent=None):
        QScrollBar.__init__(self, parent)
        self.ani = QPropertyAnimation()
        self.ani.setTargetObject(self)
        self.ani.setPropertyName(b"value")
        self.ani.setEasingCurve(QEasingCurve.OutCubic)
        self.ani.setDuration(400)  # 调整动画持续时间
        self.__value = self.value()
        self.ani.finished.connect(self.scrollFinished)

    def setValue(self, value: int):
        if value == self.value():
            return

        self.ani.stop()
        self.scrollFinished.emit()

        self.ani.setStartValue(self.value())
        self.ani.setEndValue(value)
        self.ani.start()

    def wheelEvent(self, e):
        # 阻止默认的滚轮事件，使用自定义的滚动逻辑
        e.ignore()


class SmoothScrollArea(QScrollArea):
    """平滑滚动区域"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vScrollBar = SmoothScrollBar()
        self.setVerticalScrollBar(self.vScrollBar)
        self.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏原始滚动条

    def wheelEvent(self, e):
        if hasattr(self.vScrollBar, 'scrollValue'):
            self.vScrollBar.scrollValue(-e.angleDelta().y())


class Plugin:
    def __init__(self, cw_contexts, method):
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        self.scroll_position = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.auto_scroll)
        self.timer.start(80)  # 调整滚动速度

        # 新增定时器用于延迟重试
        self.retry_timer = QTimer()
        self.retry_timer.timeout.connect(self.update_yiyan)

        # 初始显示加载状态
        self.show_loading()

    def show_loading(self):
        """显示加载状态"""
        self.update_widget_content("加载中，请稍后...", "LaoShui")

    def update_yiyan(self):
        """启动异步更新每日一言"""
        self.show_loading()
        self.retry_timer.stop()

        self.worker_thread = FetchThread()
        self.worker_thread.fetch_finished.connect(self.handle_success)
        self.worker_thread.fetch_failed.connect(self.handle_failure)
        self.worker_thread.start()

    def handle_success(self, data):
        """处理成功响应"""
        content = data.get("content", "无法获取一言信息。")
        author = data.get("author", "未知作者")
        self.update_widget_content(content, author)

    def handle_failure(self):
        """处理失败情况"""
        logger.warning("重试3次失败，5分钟后自动重试")
        self.update_widget_content("网络连接异常，5分钟后自动重试", "LaoShui")
        self.retry_timer.start(5 * 60 * 1000)  # 5分钟重试

    def update_widget_content(self, content, author):
        """更新小组件内容（线程安全）"""
        self.test_widget = self.method.get_widget(WIDGET_CODE)
        if not self.test_widget:
            logger.error(f"小组件未找到，WIDGET_CODE: {WIDGET_CODE}")
            return

        # 使用QTimer.singleShot确保在主线程执行UI操作
        QTimer.singleShot(0, lambda: self._update_ui(content, author))

    def _update_ui(self, content, author):
        """实际执行UI更新的方法"""
        content_layout = self.find_child_layout(self.test_widget, 'contentLayout')
        if not content_layout:
            logger.error("未能找到小组件的'contentLayout'布局")
            return

        content_layout.setSpacing(5)
        self.method.change_widget_content(WIDGET_CODE, WIDGET_NAME, WIDGET_NAME)

        # 清除旧内容
        self.clear_existing_content(content_layout)

        # 创建滚动区域并设置内容
        scroll_area = self.create_scroll_area(content, author)
        if scroll_area:
            content_layout.addWidget(scroll_area)
            logger.success('每日一言内容更新成功！')
        else:
            logger.error("滚动区域创建失败")

    @staticmethod
    def find_child_layout(widget, layout_name):
        """根据名称查找并返回布局"""
        return widget.findChild(QHBoxLayout, layout_name)

    def create_scroll_area(self, content, author):
        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_content_layout)
        self.clear_existing_content(scroll_content_layout)

        if isDarkTheme():
            font_color = "#FFFFFF"  # 白色字体
        else:
            font_color = "#000000"  # 黑色字体

        content_label = QLabel(content)
        content_label.setAlignment(Qt.AlignCenter)
        content_label.setWordWrap(True)  # 自动换行
        content_label.setStyleSheet(f"""
            font-size: 16px;
            color: {font_color};
            padding: 10px;
            font-weight: bold;
            background: none;
        """)
        scroll_content_layout.addWidget(content_label)

        author_label = QLabel(f"—— {author}")
        author_label.setAlignment(Qt.AlignRight)
        author_label.setStyleSheet(f"""
            font-size: 12px;
            color: {font_color};
            padding-right: 10px;
            font-weight: bold;
            background: none;
        """)
        scroll_content_layout.addWidget(author_label)

        scroll_area.setWidget(scroll_content)
        return scroll_area

    @staticmethod
    def clear_existing_content(content_layout):
        """清除布局中的旧内容"""
        while content_layout.count() > 0:
            item = content_layout.takeAt(0)
            if item:
                child_widget = item.widget()
                if child_widget:
                    child_widget.deleteLater()  # 确保子组件被销毁

    def auto_scroll(self):
        """自动滚动功能"""
        if not self.test_widget:
            # logger.warning("自动滚动失败，小组件未初始化或已被销毁") 不能加log不然没启用的话日志就被刷爆了
            return

        # 查找 SmoothScrollArea
        scroll_area = self.test_widget.findChild(SmoothScrollArea)
        if not scroll_area:
            # logger.warning("无法找到 SmoothScrollArea，停止自动滚动") 实际使用不加log不然有错日志就被刷爆了
            return

        # 查找滚动条
        vertical_scrollbar = scroll_area.verticalScrollBar()
        if not vertical_scrollbar:
            # logger.warning("无法找到垂直滚动条，停止自动滚动") 实际使用不加log不然有错日志就被刷爆了
            return

        # 执行滚动逻辑
        max_value = vertical_scrollbar.maximum()
        if self.scroll_position >= max_value:
            self.scroll_position = 0  # 滚动回顶部
        else:
            self.scroll_position += 1  # 向下滚动

        vertical_scrollbar.setValue(self.scroll_position)

    def execute(self):
        """首次执行"""
        self.update_yiyan()
