import time
import requests
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QWidget, QVBoxLayout
from loguru import logger
from qfluentwidgets import isDarkTheme

WIDGET_CODE = 'widget_yiyan.ui'
WIDGET_NAME = '每日一言 | LaoShui'
WIDGET_WIDTH = 360
API_URL = "https://api.codelife.cc/yiyan/info?lang=cn"

# 模拟 Edge 浏览器的 User-Agent
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 '
        'Edge/91.0.864.64'
    )
}


class Plugin:
    def __init__(self, cw_contexts, method):
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        # 初始化时更新一次一言
        self.update_yiyan()

        # 定时器：每100毫秒更新一次滚动位置
        self.scroll_position = 0
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self.scroll_timer.start(100)  # 每100毫秒执行一次滚动

    @staticmethod
    def fetch_yiyan():
        """请求一言接口并获取数据，带重试机制"""
        retry_count = 0
        max_retries = 3
        while retry_count < max_retries:
            try:
                # 使用模拟的 User-Agent 发送请求
                response = requests.get(API_URL, headers=HEADERS, proxies={'http': None, 'https': None})  # 禁用代理，模拟浏览器请求
                response.raise_for_status()  # 如果状态码不是200，则抛出异常
                logger.debug(f"API 响应内容: {response.text}")  # 打印响应内容，检查返回的数据
                data = response.json().get("data", {})
                if data:
                    return data
                else:
                    logger.warning("获取的数据为空，正在重试...")
            except requests.RequestException as e:
                logger.error(f"请求一言信息失败: {e}")

            retry_count += 1
            time.sleep(2)

        # 如果3次重试都失败，则等待5分钟后再尝试
        logger.warning(f"重试 {max_retries} 次失败，等待5分钟后再试...")
        time.sleep(5 * 60)  # 等待5分钟
        return Plugin.fetch_yiyan()

    def update_yiyan(self):
        """更新每日一言"""
        yiyan_data = self.fetch_yiyan()
        if yiyan_data:
            # 提取一言内容和作者信息
            content = yiyan_data.get("content", "无法获取一言信息。")
            author = yiyan_data.get("author", "未知作者")
            pic_url = yiyan_data.get("pic_url", "")  # 不会写 先放着

            # 更新小组件内容
            self.update_widget_content(content, author)
        else:
            # 如果获取失败，显示默认内容
            self.update_widget_content("无法获取一言信息，请稍后再试。", "未知作者")

    def update_widget_content(self, content, author):
        """更新小组件内容"""
        self.test_widget = self.method.get_widget(WIDGET_CODE)
        if self.test_widget:
            content_layout = self.find_child_layout(self.test_widget, 'contentLayout')
            content_layout.setSpacing(5)

            # 修改标题
            self.method.change_widget_content(WIDGET_CODE, WIDGET_NAME, WIDGET_NAME)
            # 清除旧内容
            self.clear_existing_content(content_layout)

            # 创建滚动区域并设置内容
            scroll_area = self.create_scroll_area(content, author)
            content_layout.addWidget(scroll_area)

        logger.success('每日一言内容更新成功！')

    @staticmethod
    def find_child_layout(widget, layout_name):
        """根据名称查找并返回布局"""
        return widget.findChild(QHBoxLayout, layout_name)

    def create_scroll_area(self, content, author):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏滚动条

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_content_layout)

        # 清除旧内容，避免重复或空白行
        self.clear_existing_content(scroll_content_layout)

        # 根据当前主题设置样式
        if isDarkTheme():
            font_color = "#FFFFFF"  # 白色字体
        else:
            font_color = "#000000"  # 黑色字体

        # 一言内容标签
        content_label = QLabel(content)
        content_label.setAlignment(Qt.AlignCenter)
        content_label.setWordWrap(True)  # 自动换行
        content_label.setStyleSheet(f"font-size: 16px; color: {font_color}; padding: 10px; font-weight: bold;")

        scroll_content_layout.addWidget(content_label)

        # 作者标签
        author_label = QLabel(f"—— {author}")
        author_label.setAlignment(Qt.AlignRight)
        author_label.setStyleSheet(f"font-size: 12px; color: {font_color}; padding-right: 10px; font-weight: bold;")
        scroll_content_layout.addWidget(author_label)

        scroll_area.setWidget(scroll_content)
        return scroll_area

    @staticmethod
    def clear_existing_content(content_layout):
        """清除布局中的旧内容"""
        for i in range(content_layout.count()):
            child_widget = content_layout.itemAt(i).widget()
            if child_widget:
                child_widget.deleteLater()

    def auto_scroll(self):
        """自动滚动功能"""
        if self.test_widget is None:  # 若小组件不存在，则不执行
            return
        scroll_area = self.test_widget.findChild(QScrollArea)
        if scroll_area:
            vertical_scrollbar = scroll_area.verticalScrollBar()
            if vertical_scrollbar:
                max_value = vertical_scrollbar.maximum()
                # 如果滚动条已经到达底部，滚动回顶部
                if self.scroll_position >= max_value:
                    vertical_scrollbar.setValue(0)  # 滚动到顶部
                    self.scroll_position = 0
                else:
                    # 否则继续向下滚动
                    self.scroll_position += 1
                    vertical_scrollbar.setValue(self.scroll_position)

    def execute(self):
        """首次执行，加载每日一言"""
        self.update_yiyan()
