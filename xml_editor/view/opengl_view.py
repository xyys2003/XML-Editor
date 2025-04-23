"""
OpenGL视图

负责场景的3D渲染和用户交互。
"""

from PyQt5.QtWidgets import QOpenGLWidget, QSizePolicy
from PyQt5.QtCore import Qt, QSize, QPoint, pyqtSignal
from PyQt5.QtGui import QMouseEvent, QWheelEvent, QKeyEvent

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *  # 添加GLUT库导入

from ..model.geometry import GeometryType, OperationMode, TransformMode

# 初始化GLUT
try:
    glutInit()
except Exception as e:
    print(f"警告: 无法初始化GLUT: {e}")
    # 定义替代函数
    def _draw_cube_alternative():
        """替代glutSolidCube的立方体绘制函数"""
        vertices = [
            # 前面
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
            # 后面
            [-1, -1, -1], [-1, 1, -1], [1, 1, -1], [1, -1, -1],
            # 上面
            [-1, 1, -1], [-1, 1, 1], [1, 1, 1], [1, 1, -1],
            # 下面
            [-1, -1, -1], [1, -1, -1], [1, -1, 1], [-1, -1, 1],
            # 右面
            [1, -1, -1], [1, 1, -1], [1, 1, 1], [1, -1, 1],
            # 左面
            [-1, -1, -1], [-1, -1, 1], [-1, 1, 1], [-1, 1, -1]
        ]
        
        normals = [
            [0, 0, 1], [0, 0, 1], [0, 0, 1], [0, 0, 1],  # 前面
            [0, 0, -1], [0, 0, -1], [0, 0, -1], [0, 0, -1],  # 后面
            [0, 1, 0], [0, 1, 0], [0, 1, 0], [0, 1, 0],  # 上面
            [0, -1, 0], [0, -1, 0], [0, -1, 0], [0, -1, 0],  # 下面
            [1, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0],  # 右面
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0]  # 左面
        ]
        
        faces = [
            [0, 1, 2, 3],  # 前面
            [4, 5, 6, 7],  # 后面
            [8, 9, 10, 11],  # 上面
            [12, 13, 14, 15],  # 下面
            [16, 17, 18, 19],  # 右面
            [20, 21, 22, 23]   # 左面
        ]
        
        glBegin(GL_QUADS)
        for face in faces:
            for i in face:
                glNormal3fv(normals[i])
                glVertex3fv([v * 1.0 for v in vertices[i]])
        glEnd()
    
    # 使用替代函数
    glutSolidCube = lambda size: (_draw_cube_alternative(), None)[1]
    
    def _draw_sphere_alternative(radius, slices, stacks):
        """替代glutSolidSphere的球体绘制函数"""
        quadric = gluNewQuadric()
        gluQuadricDrawStyle(quadric, GLU_FILL)
        gluQuadricNormals(quadric, GLU_SMOOTH)
        gluSphere(quadric, radius, slices, stacks)
        gluDeleteQuadric(quadric)
    
    glutSolidSphere = _draw_sphere_alternative

class OpenGLView(QOpenGLWidget):
    """
    OpenGL视图类
    
    负责渲染3D场景并处理用户交互
    """
    # 信号
    mousePressed = pyqtSignal(QMouseEvent)
    mouseReleased = pyqtSignal(QMouseEvent)
    mouseMoved = pyqtSignal(QMouseEvent)
    mouseWheel = pyqtSignal(QWheelEvent)
    keyPressed = pyqtSignal(QKeyEvent)
    
    def __init__(self, scene_viewmodel, parent=None):
        """
        初始化OpenGL视图
        
        参数:
            scene_viewmodel: 场景视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        self._scene_viewmodel = scene_viewmodel
        
        # 设置尺寸策略
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(400, 300))
        
        # 鼠标交互相关
        self._last_mouse_pos = QPoint()
        self._is_mouse_pressed = False
        self._is_shift_pressed = False
        
        # 摄像机参数
        self._camera_distance = 10.0
        self._camera_rotation_x = 30.0  # 俯仰角
        self._camera_rotation_y = -45.0  # 偏航角
        self._camera_target = np.array([0.0, 0.0, 0.0])
        
        # 连接信号
        self._scene_viewmodel.geometriesChanged.connect(self.update)
        self._scene_viewmodel.selectionChanged.connect(self.update)
        
        # 捕获焦点
        self.setFocusPolicy(Qt.StrongFocus)
    
    def minimumSizeHint(self):
        """返回建议的最小尺寸"""
        return QSize(200, 150)
    
    def sizeHint(self):
        """返回建议的尺寸"""
        return QSize(640, 480)
    
    def initializeGL(self):
        """初始化OpenGL上下文"""
        glClearColor(0.2, 0.2, 0.2, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        
        # 设置光源
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        
        # 启用混合（用于半透明物体）
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    
    def resizeGL(self, width, height):
        """处理窗口大小变化事件"""
        glViewport(0, 0, width, height)
        self._update_projection(width, height)
    
    def paintGL(self):
        """渲染场景"""
        # 清除缓冲区
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # 设置投影矩阵
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        self._update_projection(self.width(), self.height())
        
        # 设置模型视图矩阵
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # 应用摄像机变换
        self._apply_camera_transform()
        
        # 更新摄像机配置到场景视图模型
        self._update_camera_config()
        
        # 绘制网格
        self._draw_grid()
        
        # 绘制坐标轴
        self._draw_axes()
        
        # 绘制场景中的几何体
        for geometry in self._scene_viewmodel.geometries:
            self._draw_geometry(geometry)
    
    def _update_projection(self, width, height):
        """更新投影矩阵"""
        aspect = width / height if height > 0 else 1.0
        gluPerspective(45.0, aspect, 0.1, 100.0)
    
    def _apply_camera_transform(self):
        """应用摄像机变换"""
        # 计算摄像机位置
        camera_x = self._camera_target[0] + self._camera_distance * np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        camera_y = self._camera_target[1] + self._camera_distance * np.sin(np.radians(self._camera_rotation_x))
        camera_z = self._camera_target[2] + self._camera_distance * np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        
        # 设置视图
        gluLookAt(
            camera_x, camera_y, camera_z,                   # 摄像机位置
            self._camera_target[0], self._camera_target[1], self._camera_target[2],  # 目标点
            0.0, 1.0, 0.0                                  # 上向量
        )
    
    def _update_camera_config(self):
        """更新摄像机配置到场景视图模型"""
        # 计算摄像机位置
        camera_x = self._camera_target[0] + self._camera_distance * np.cos(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        camera_y = self._camera_target[1] + self._camera_distance * np.sin(np.radians(self._camera_rotation_x))
        camera_z = self._camera_target[2] + self._camera_distance * np.sin(np.radians(self._camera_rotation_y)) * np.cos(np.radians(self._camera_rotation_x))
        
        camera_position = np.array([camera_x, camera_y, camera_z])
        
        # 获取当前的投影矩阵和模型视图矩阵
        projection_matrix = glGetDoublev(GL_PROJECTION_MATRIX)
        modelview_matrix = glGetDoublev(GL_MODELVIEW_MATRIX)
        
        # 更新场景视图模型的摄像机配置
        self._scene_viewmodel.set_camera_config({
            'position': camera_position,
            'target': self._camera_target,
            'up': np.array([0.0, 1.0, 0.0]),
            'projection_matrix': projection_matrix,
            'view_matrix': modelview_matrix
        })
    
    def _draw_grid(self):
        """绘制地面网格"""
        glDisable(GL_LIGHTING)
        glColor4f(0.5, 0.5, 0.5, 0.5)  # 灰色
        
        glBegin(GL_LINES)
        
        # 绘制x轴线
        for i in range(-10, 11):
            glVertex3f(i, 0, -10)
            glVertex3f(i, 0, 10)
        
        # 绘制z轴线
        for i in range(-10, 11):
            glVertex3f(-10, 0, i)
            glVertex3f(10, 0, i)
            
        glEnd()
        
        glEnable(GL_LIGHTING)
    
    def _draw_axes(self):
        """绘制坐标轴"""
        glDisable(GL_LIGHTING)
        
        glBegin(GL_LINES)
        
        # X轴（红色）
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(1, 0, 0)
        
        # Y轴（绿色）
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 1, 0)
        
        # Z轴（蓝色）
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 1)
        
        glEnd()
        
        glEnable(GL_LIGHTING)
    
    def _draw_geometry(self, geometry):
        """
        递归绘制几何体和其子对象
        
        参数:
            geometry: 要绘制的几何体
        """
        # 保存当前矩阵
        glPushMatrix()
        
        # 应用几何体的变换
        if hasattr(geometry, 'transform_matrix'):
            # 将NumPy矩阵转换为OpenGL兼容的格式
            transform = geometry.transform_matrix.T.flatten().tolist()
            glMultMatrixf(transform)
        
        # 绘制几何体
        if hasattr(geometry, 'type'):
            if geometry.type == 'group':
                # 绘制组的包围盒（半透明）
                self._draw_wireframe_cube(highlight=geometry == self._scene_viewmodel.selected_geometry)
            else:
                # 根据几何体类型和选中状态绘制
                self._draw_geometry_by_type(geometry, geometry == self._scene_viewmodel.selected_geometry)
        
        # 递归绘制子对象
        if hasattr(geometry, 'children'):
            for child in geometry.children:
                self._draw_geometry(child)
        
        # 恢复矩阵
        glPopMatrix()
    
    def _draw_geometry_by_type(self, geometry, selected):
        """
        根据几何体类型绘制
        
        参数:
            geometry: 要绘制的几何体
            selected: 是否被选中
        """
        # 设置材质
        color = geometry.material.color
        
        # 如果被选中，增加亮度
        if selected:
            glColor4f(min(color[0] + 0.2, 1.0), min(color[1] + 0.2, 1.0), min(color[2] + 0.2, 1.0), color[3])
        else:
            glColor4f(color[0], color[1], color[2], color[3])
        
        # 根据几何体类型绘制
        if geometry.type == GeometryType.BOX.value:
            self._draw_box()
        elif geometry.type == GeometryType.SPHERE.value:
            self._draw_sphere()
        elif geometry.type == GeometryType.CYLINDER.value:
            self._draw_cylinder()
        elif geometry.type == GeometryType.CAPSULE.value:
            self._draw_capsule()
        elif geometry.type == GeometryType.PLANE.value:
            self._draw_plane()
        else:
            # 默认使用立方体
            self._draw_box()
        
        # 如果被选中，绘制包围盒
        if selected:
            self._draw_wireframe_cube(highlight=True)
    
    def _draw_box(self):
        """绘制立方体"""
        glPushMatrix()
        glScalef(1.0, 1.0, 1.0)
        try:
            glutSolidCube(2.0)
        except Exception:
            _draw_cube_alternative()
        glPopMatrix()
    
    def _draw_sphere(self):
        """绘制球体"""
        glPushMatrix()
        sphere_radius = 1.0
        sphere_slices = 20
        sphere_stacks = 20
        glutSolidSphere(sphere_radius, sphere_slices, sphere_stacks)
        glPopMatrix()
    
    def _draw_cylinder(self):
        """绘制圆柱体"""
        glPushMatrix()
        cylinder_radius = 1.0
        cylinder_height = 2.0
        cylinder_slices = 20
        cylinder_stacks = 1
        
        gluCylinder(
            gluNewQuadric(),      # 二次曲面对象
            cylinder_radius,      # 底部半径
            cylinder_radius,      # 顶部半径
            cylinder_height,      # 高度
            cylinder_slices,      # 径向细分
            cylinder_stacks       # 高度细分
        )
        
        # 绘制底部和顶部圆盖
        gluDisk(gluNewQuadric(), 0.0, cylinder_radius, cylinder_slices, 1)
        
        glPushMatrix()
        glTranslatef(0.0, 0.0, cylinder_height)
        gluDisk(gluNewQuadric(), 0.0, cylinder_radius, cylinder_slices, 1)
        glPopMatrix()
        
        glPopMatrix()
    
    def _draw_capsule(self):
        """绘制胶囊体（简化为圆柱和两个半球）"""
        glPushMatrix()
        capsule_radius = 1.0
        capsule_height = 2.0
        capsule_slices = 20
        capsule_stacks = 1
        
        # 绘制中间圆柱部分
        gluCylinder(
            gluNewQuadric(),      # 二次曲面对象
            capsule_radius,       # 底部半径
            capsule_radius,       # 顶部半径
            capsule_height,       # 高度
            capsule_slices,       # 径向细分
            capsule_stacks        # 高度细分
        )
        
        # 绘制底部半球
        sphere_stacks = 10
        gluSphere(gluNewQuadric(), capsule_radius, capsule_slices, sphere_stacks)
        
        # 绘制顶部半球
        glPushMatrix()
        glTranslatef(0.0, 0.0, capsule_height)
        gluSphere(gluNewQuadric(), capsule_radius, capsule_slices, sphere_stacks)
        glPopMatrix()
        
        glPopMatrix()
    
    def _draw_plane(self):
        """绘制平面"""
        glPushMatrix()
        glScalef(1.0, 0.01, 1.0)  # 使平面非常薄
        try:
            glutSolidCube(2.0)
        except Exception:
            _draw_cube_alternative()
        glPopMatrix()
    
    def _draw_wireframe_cube(self, highlight=False):
        """
        绘制线框立方体
        
        参数:
            highlight: 是否高亮显示
        """
        glDisable(GL_LIGHTING)
        
        if highlight:
            glColor4f(1.0, 1.0, 0.0, 1.0)  # 黄色
            glLineWidth(2.0)
        else:
            glColor4f(0.5, 0.5, 0.5, 0.7)  # 灰色
            glLineWidth(1.0)
        
        glBegin(GL_LINES)
        
        # 底面
        glVertex3f(-1, -1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, -1, 1)
        glVertex3f(1, -1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, -1, -1)
        
        # 顶面
        glVertex3f(-1, 1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, 1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(-1, 1, 1)
        glVertex3f(-1, 1, 1)
        glVertex3f(-1, 1, -1)
        
        # 连接底面和顶面
        glVertex3f(-1, -1, -1)
        glVertex3f(-1, 1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, -1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, 1, 1)
        
        glEnd()
        
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        self._last_mouse_pos = event.pos()
        self._is_mouse_pressed = True
        
        # 如果是左键且处于观察模式，尝试选择对象
        if event.button() == Qt.LeftButton and self._scene_viewmodel.operation_mode == OperationMode.OBSERVE:
            self._scene_viewmodel.select_at(event.x(), event.y(), self.width(), self.height())
        
        # 发出信号
        self.mousePressed.emit(event)
        
        # 接收后续的鼠标移动事件
        self.setMouseTracking(True)
    
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        self._is_mouse_pressed = False
        
        # 发出信号
        self.mouseReleased.emit(event)
        
        # 不再跟踪鼠标移动
        self.setMouseTracking(False)
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        dx = event.x() - self._last_mouse_pos.x()
        dy = event.y() - self._last_mouse_pos.y()
        
        # 如果鼠标按下，根据当前模式执行不同操作
        if self._is_mouse_pressed:
            # 处理摄像机旋转（左键拖动）
            if event.buttons() & Qt.LeftButton:
                self._camera_rotation_y += dx * 0.5
                self._camera_rotation_x = max(-90, min(90, self._camera_rotation_x + dy * 0.5))
                self.update()
            
            # 处理摄像机平移（右键拖动）
            elif event.buttons() & Qt.RightButton:
                # 计算平移向量
                right_vector = np.array([
                    np.cos(np.radians(self._camera_rotation_y - 90)),
                    0,
                    np.sin(np.radians(self._camera_rotation_y - 90))
                ])
                
                up_vector = np.array([0, 1, 0])
                
                # 应用平移
                self._camera_target -= right_vector * dx * 0.001 * self._camera_distance
                self._camera_target += up_vector * dy * 0.001 * self._camera_distance
                
                self.update()
        
        # 更新鼠标位置
        self._last_mouse_pos = event.pos()
        
        # 发出信号
        self.mouseMoved.emit(event)
    
    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        # 更新摄像机距离
        delta = event.angleDelta().y() / 120  # 标准化滚轮步长
        self._camera_distance *= 0.9 ** delta  # 放大/缩小10%
        
        # 限制距离范围
        self._camera_distance = max(0.1, min(100.0, self._camera_distance))
        
        self.update()
        
        # 发出信号
        self.mouseWheel.emit(event)
    
    def keyPressEvent(self, event):
        """处理键盘按下事件"""
        # 处理Shift键
        if event.key() == Qt.Key_Shift:
            self._is_shift_pressed = True
        
        # 发出信号
        self.keyPressed.emit(event)
    
    def keyReleaseEvent(self, event):
        """处理键盘释放事件"""
        # 处理Shift键
        if event.key() == Qt.Key_Shift:
            self._is_shift_pressed = False
    
    def reset_camera(self):
        """重置摄像机到默认位置"""
        self._camera_distance = 10.0
        self._camera_rotation_x = 30.0
        self._camera_rotation_y = -45.0
        self._camera_target = np.array([0.0, 0.0, 0.0])
        self.update() 