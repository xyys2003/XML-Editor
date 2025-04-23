# MuJoCo 场景编辑器

这是一个基于PyQt5和OpenGL开发的图形界面编辑器，专门用于创建和编辑MuJoCo物理引擎的场景描述语言（MJCF）文件。该编辑器提供了直观的3D界面，使用户能够可视化地创建、编辑和组织MuJoCo场景，无需手动编写复杂的XML代码。

## 功能特点

- **可视化编辑**：直观的3D视图，实时预览场景效果
- **基础几何体支持**：创建和编辑多种几何体类型
  - 盒子（Box）
  - 球体（Sphere）
  - 圆柱体（Cylinder）
  - 胶囊体（Capsule）
  - 平面（Plane）
- **变换工具**：完整的对象变换功能
  - 平移（Translate）
  - 旋转（Rotate）
  - 缩放（Scale）
  - 支持全局/局部坐标系切换
- **属性编辑**：实时编辑对象属性
  - 几何属性（尺寸、位置、旋转）
  - 材质属性（颜色、反射率）
- **层级结构管理**：通过树状视图管理场景层级
- **导入/导出**：支持MuJoCo XML格式的导入和导出
- **射线投射系统**：精确的对象选择和交互
- **自定义控制器**：为不同操作模式提供专用的3D控制器

## 安装

### 系统要求

- 操作系统：Windows/macOS/Linux
- Python >= 3.7
- 显卡：支持OpenGL 3.3或更高版本

### 依赖

- Python >= 3.7
- PyQt5 >= 5.15.0
- NumPy >= 1.20.0
- PyOpenGL >= 3.1.0
- PyOpenGL_accelerate >= 3.1.0（可选，提高性能）

### 安装步骤

1. 克隆仓库：
   ```
   git clone https://github.com/yourusername/xml-editor.git
   cd xml-editor
   ```

2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

   或直接安装包：
   ```
   pip install .
   ```

   开发模式安装：
   ```
   pip install -e .
   ```

## 使用说明

### 启动程序

```
python -m xml_editor.main
```

### 基本操作

#### 场景导航
- **旋转视图**：按住鼠标左键拖动
- **平移视图**：按住鼠标右键拖动
- **缩放视图**：滚动鼠标滚轮
- **取消选择**：按Esc键

#### 对象选择与编辑
- **选择对象**：左键点击场景中的对象
- **查看属性**：在右侧属性面板中查看选中对象的属性
- **编辑属性**：在属性面板中修改参数，实时更新场景

#### 变换操作
- **选择操作模式**：在控制面板中选择平移、旋转或缩放模式
- **使用控制器**：点击并拖动场景中的变换控制器（红、绿、蓝轴）
- **切换坐标系**：按空格键在全局坐标系和局部坐标系之间切换

#### 创建对象
- **添加几何体**：使用控制面板中的按钮添加各种几何体
- **调整层级**：在层级树中拖放对象调整父子关系

#### 文件操作
- **新建场景**：文件菜单 -> 新建
- **打开场景**：文件菜单 -> 打开
- **保存场景**：文件菜单 -> 保存/另存为
- **导出MuJoCo XML**：文件菜单 -> 导出MuJoCo XML

## 代码架构

项目采用MVVM（Model-View-ViewModel）架构设计：

### 架构图

```
+------------------+    +---------------------+    +------------------+
|      Model       |<-->|     ViewModel       |<-->|      View        |
+------------------+    +---------------------+    +------------------+
| - Geometry       |    | - SceneViewModel    |    | - MainWindow     |
| - Material       |    | - ControlViewModel  |    | - OpenGLView     |
| - GeometryType   |    |                     |    | - PropertyView   |
| - OperationMode  |    |                     |    | - ControlPanel   |
+------------------+    +---------------------+    +------------------+
```

### 信号和槽关系

```
+--------------------+  selectionChanged   +--------------------+
|   SceneViewModel   |--------------------->|     OpenGLView     |
+--------------------+  geometriesChanged  +--------------------+
          ^             operationModeChanged        |
          |                                         |
          |           objectSelected               |
          +-------------------------------------+
                                                |
+--------------------+  operationModeChanged  +--------------------+
| ControlViewModel   |--------------------->  |   ControlPanel     |
+--------------------+                       +--------------------+
          ^                                         |
          |           modeButtonClicked            |
          +-------------------------------------+

+--------------------+  objectChanged       +--------------------+
|   SceneViewModel   |--------------------->|    PropertyView    |
+--------------------+  selectionChanged    +--------------------+
          ^                                         |
          |           propertyValueChanged          |
          +-------------------------------------+
```

### 类包含和继承关系

```
                   QMainWindow
                        |
                        v
                    MainWindow
                   /    |    \
                  /     |     \
                 v      v      v
        OpenGLView  PropertyView  ControlPanel
            |            |            |
            v            v            v
      QOpenGLWidget   QWidget       QWidget
            |
            v
     SceneViewModel
        /      \
       /        \
      v          v
Geometry      Material
```

## 类的职责

### 模型层
- `Geometry`: 定义几何体的属性和变换
- `Material`: 定义材质属性（颜色、反射率等）
- `GeometryRaycaster`: 实现射线与几何体的求交算法

### 视图模型层
- `SceneViewModel`: 管理场景状态，处理场景中对象的选择和编辑
- `ControlViewModel`: 管理编辑器控制状态，如操作模式

### 视图层
- `MainWindow`: 主应用窗口，协调各个UI组件
- `OpenGLView`: OpenGL渲染视图，处理3D场景渲染和交互
- `PropertyView`: 对象属性编辑面板
- `ControlPanel`: 操作控制面板，提供工具选择

## 贡献指南

欢迎对本项目提出建议和贡献代码。请遵循以下步骤：

1. Fork本仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建Pull Request

## 许可

本项目采用MIT许可证，详情请参阅[LICENSE](LICENSE)文件。 