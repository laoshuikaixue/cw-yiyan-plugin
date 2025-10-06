import time
import requests
from datetime import datetime, timedelta
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

    def scrollValue(self, delta):
        """滚动一定值"""
        new_value = self.value() - delta / 120 * 40
        new_value = max(0, min(new_value, self.maximum()))
        self.setValue(int(new_value))


class SmoothScrollArea(QScrollArea):
    """平滑滚动区域"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vScrollBar = SmoothScrollBar()
        self.setVerticalScrollBar(self.vScrollBar)
        self.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏原始滚动条
        self.content_widget = None
        self.content = ""
        self.author = ""
        self.last_added_pos = 0
        self.is_infinite = True  # 是否启用无限滚动

    def wheelEvent(self, e):
        if hasattr(self.vScrollBar, 'scrollValue'):
            self.vScrollBar.scrollValue(-e.angleDelta().y())

    def set_content(self, content, author, font_color="#000000"):
        """设置内容并保存，用于后续无限滚动"""
        self.content = content
        self.author = author
        self.font_color = font_color

        # 初始化内容widget
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)

        # 添加初始内容
        self.add_content_block(content_layout)
        # 再添加一个内容块以便滚动
        if self.is_infinite:
            self.add_content_block(content_layout)

        # 设置滚动区域的widget
        self.setWidget(self.content_widget)

        # 保存最后添加的位置
        self.last_added_pos = content_layout.count()

    def add_content_block(self, layout):
        """添加一个内容块（包括内容和作者）"""
        content_label = QLabel(self.content)
        content_label.setAlignment(Qt.AlignCenter)
        content_label.setWordWrap(True)
        content_label.setStyleSheet(f"""
            font-size: 16px;
            color: {self.font_color};
            padding: 10px;
            font-weight: bold;
            background: none;
        """)
        layout.addWidget(content_label)

        author_label = QLabel(f"—— {self.author}")
        author_label.setAlignment(Qt.AlignRight)
        author_label.setStyleSheet(f"""
            font-size: 12px;
            color: {self.font_color};
            padding-right: 10px;
            font-weight: bold;
            background: none;
        """)
        layout.addWidget(author_label)

    def check_scroll_position(self):
        """检查滚动位置，如果接近底部则添加更多内容"""
        if not self.is_infinite or not self.content_widget:
            return

        scrollbar = self.verticalScrollBar()
        if scrollbar.value() > scrollbar.maximum() * 0.7:  # 当滚动超过70%时
            layout = self.content_widget.layout()
            self.add_content_block(layout)
            self.last_added_pos = layout.count()


class Plugin:
    def __init__(self, cw_contexts, method):
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        self.scroll_position = 0
        self.enable_scrolling = False  # 添加控制滚动的标志
        self.timer = QTimer()
        self.timer.timeout.connect(self.auto_scroll)
        self.timer.start(80)  # 调整滚动速度

        # 新增定时器用于延迟重试
        self.retry_timer = QTimer()
        self.retry_timer.timeout.connect(self.update_yiyan)

        # 新增每日定时更新定时器
        self.daily_timer = QTimer()
        self.daily_timer.timeout.connect(self.daily_update)
        
        # 添加每日更新状态跟踪
        self.last_update_date = None
        
        self.setup_daily_update()

        # 初始显示加载状态
        self.show_loading()

    def setup_daily_update(self):
        """设置每日1点自动更新"""
        now = datetime.now()
        # 计算下一个1点的时间
        next_update = now.replace(hour=1, minute=0, second=0, microsecond=0)
        
        # 如果当前时间已经过了今天的1点，则设置为明天1点
        if now >= next_update:
            next_update += timedelta(days=1)
        
        # 计算距离下次更新的毫秒数
        time_until_update = (next_update - now).total_seconds() * 1000
        
        # 设置单次定时器，到时间后触发更新并重新设置下一次
        self.daily_timer.setSingleShot(True)
        self.daily_timer.start(int(time_until_update))
        
        logger.info(f"下次自动更新时间: {next_update.strftime('%Y-%m-%d %H:%M:%S')}")

    def daily_update(self):
        """每日定时更新"""
        today = datetime.now().date()
        
        # 检查今天是否已经更新过
        if self.last_update_date == today:
            logger.info("今日已更新过，跳过本次更新")
            self.setup_daily_update()  # 重新设置下一次更新
            return
        
        # 执行更新
        self.update_yiyan()
        
        # 重新设置下一次更新
        self.setup_daily_update()

    def show_loading(self):
        """显示加载状态"""
        self.enable_scrolling = False  # 加载中禁用滚动
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
        self.enable_scrolling = True  # 成功获取数据后启用滚动
        self.update_widget_content(content, author)
        
        # 记录更新日期
        self.last_update_date = datetime.now().date()
        logger.info(f"一言更新成功，更新日期: {self.last_update_date}")

    def handle_failure(self):
        """处理失败情况"""
        logger.warning("重试3次失败，5分钟后自动重试")
        self.enable_scrolling = False  # 失败时禁用滚动
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

        if isDarkTheme():
            font_color = "#FFFFFF"  # 白色字体
        else:
            font_color = "#000000"  # 黑色字体

        # 使用新的设置内容方法
        scroll_area.set_content(content, author, font_color)
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
        if not self.test_widget or not self.enable_scrolling:
            return

        # 查找 SmoothScrollArea
        scroll_area = self.test_widget.findChild(SmoothScrollArea)
        if not scroll_area:
            return

        # 查找滚动条
        vertical_scrollbar = scroll_area.verticalScrollBar()
        if not vertical_scrollbar:
            return

        # 执行滚动逻辑
        max_value = vertical_scrollbar.maximum()
        if max_value > 0 and self.scroll_position >= max_value:
            self.scroll_position = 0  # 滚动回顶部
        elif max_value == 0:
            self.scroll_position = 0  # 防止 maximum() 为 0 的情况
        else:
            self.scroll_position += 1  # 向下滚动

        vertical_scrollbar.setValue(self.scroll_position)

        # 检查是否需要添加更多内容
        scroll_area.check_scroll_position()

    def execute(self):
        """首次执行"""
        self.update_yiyan()
