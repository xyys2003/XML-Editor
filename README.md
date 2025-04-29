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
   git clone https://github.com/xyys2003/xml-editor.git
   cd xml-editor
   ```

2. 安装依赖：
   ```
   pip install -r requirements.txt
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
- **取消选择**：点击场景空白处或按Esc键

#### 对象选择与编辑
- **选择对象**：左键点击场景中的对象或在层级树中点击
- **多选对象**：按住 Ctrl 键点击对象
- **查看属性**：在右侧属性面板中查看选中对象的属性
- **编辑属性**：在属性面板中修改参数，实时更新场景

#### 变换操作
- **选择操作模式**：在左侧控制面板中选择观察、平移、旋转或缩放模式
- **使用Gizmo**：在相应模式下，点击并拖动场景中出现的变换控制器（红、绿、蓝轴或圆环）
- **切换坐标系**：点击控制面板中的"局部坐标系"/"全局坐标系"按钮

#### 创建对象
- **拖放创建**：从控制面板将几何体按钮拖拽到3D视图中
- **右键创建**：在层级树视图中右键点击空白处或组节点，选择新建几何体或组

#### 层级管理
- **查看层级**：在左侧层级树视图中查看
- **重命名**：在层级树中右键点击对象 -> 重命名
- **删除**：选中对象后按 Delete 键，或右键点击 -> 删除
- **组合**：选中多个对象后，右键点击 -> 组合到新组
- **调整层级**：在层级树中拖放对象到组节点或顶层（拖放到几何体为组合，拖放到组为成为子项）

#### 文件操作
- **新建场景**：文件菜单 -> 新建
- **打开XML场景**：文件菜单 -> 打开
- **保存XML场景**：文件菜单 -> 保存 / 另存为
- **创建JSON存档**：点击控制面板中的 "创建存档点"
- **加载JSON存档**：点击控制面板中的 "查看存档"，选择存档并加载

## 代码架构

项目采用**MVVM（Model-View-ViewModel）**架构设计：

### 架构图

```
+--------------------------+       +---------------------------+       +--------------------------+
|          Model           | ----> |         ViewModel         | <---> |           View           |
|  (Data & Core Logic)     |       | (State & Business Logic)  |       |  (UI Representation)     |
+--------------------------+       +---------------------------+       +--------------------------+
| - geometry.py            |       | - scene_viewmodel.py      |       | - main.py (MainWindow)   |
|   (Geometry, Group, Mat.)|       |   (Scene State, Select)   |       | - opengl_view.py         |
| - xml_parser.py          |       | - property_viewmodel.py   |       |   (OpenGLWidget)         |
|   (Load/Save XML)        |       |   (Property Logic)        |       | - property_panel.py      |
| - raycaster.py           |       | - hierarchy_viewmodel.py  |       |   (PropertyView)         |
|   (Object Picking)       |       |   (Hierarchy Logic)       |       | - hierarchy_tree.py      |
| - ...                    |       | - control_viewmodel.py    |       |   (QTreeWidget)          |
+--------------------------+       |   (Control Logic, Save)   |       | - control_panel.py       |
                                   +---------------------------+       |   (QWidget, SavesDialog) |
                                                                       +--------------------------+
```
*关系说明：ViewModel持有Model引用，处理业务逻辑和UI状态；View持有ViewModel引用，负责显示和用户交互，通过信号/槽与ViewModel通信。*

### 主要信号和槽关系 (简化示例)

```
+---------------------------+      Signals Emitted       +--------------------------+
|        ViewModel          | -------------------------> |           View           |
+---------------------------+                            +--------------------------+
| SceneViewModel            |                            |                          |
|  .geometriesChanged -------> HierarchyViewModel, OpenGLView (indirect update)     |
|  .selectionChanged -------> PropertyVM, HierarchyVM, OpenGLView, HierarchyTree   |
|  .objectChanged ----------> PropertyVM, OpenGLView, PropertyView (via PropVM)    |
|  .operationModeChanged ---> ControlVM, OpenGLView, ControlPanel (via CtrlVM)    |
|  .coordinateSystemChanged -> ControlVM, OpenGLView                                |
|                           |                            |                          |
| PropertyViewModel         |                            |                          |
|  .propertiesChanged ------> PropertyView._update_ui                                |
|                           |                            |                          |
| HierarchyViewModel        |                            |                          |
|  .hierarchyChanged -------> HierarchyTree._update_tree                           |
|  .selectionChanged -------> HierarchyTree._update_selection_from_viewmodel       |
|                           |                            |                          |
| ControlViewModel          |                            |                          |
|  .operationModeChanged ---> ControlPanel._update_operation_buttons               |
|  .saveStateCompleted -----> ControlPanel.on_save_completed                       |
|  .loadStateCompleted -----> ControlPanel.on_load_completed                       |
+---------------------------+                            +--------------------------+

+--------------------------+       UI Events/Signals     +---------------------------+
|           View           | -------------------------> |        ViewModel          |
+--------------------------+                            +---------------------------+
| OpenGLView (Mouse/Key) ---> SceneViewModel (Select, Transform, etc.)            |
| OpenGLView (Drop) --------> SceneViewModel (_create_geometry_at_position)       |
| PropertyView               |                            |                          |
|  .propertyChanged --------> PropertyViewModel.set_property                        |
| HierarchyTree              |                            |                          |
|  (UI Events, Drag/Drop) --> HierarchyViewModel (Select, Reparent, Copy/Paste...)  |
| ControlPanel               |                            |                          |
|  (Button Clicks) ---------> ControlViewModel (Set Mode, Save/Load State...)       |
+--------------------------+                            +---------------------------+

```

### 类包含和继承关系 (简化)

```
                 QMainWindow
                      |
                      v
                  MainWindow (main.py)  -----------------------> Instantiates ViewModels
                 /    |    \                                           |
                /     |     \                                          | Holds Refs
               /      |      \                                         v
              /       |       \                         +--------------------------------+
             /        |        \                        | ViewModel Classes              |
            /         |         \                       | - SceneViewModel (holds Models)|
           /          |          \                      | - PropertyViewModel            |
          /           |           \                     | - HierarchyViewModel           |
         v            v            v                    | - ControlViewModel             |
QDockWidget   QDockWidget   QDockWidget  <-- Central --> OpenGLView (opengl_view.py)    |
     |             |             |          Widget          | (QOpenGLWidget)           |
     |             |             |                          +--------------^-------------+
     |             |             |                                         | Passed To
     v             v             v                                         |
HierarchyTree  ControlPanel    PropertyPanel  <----------------------------+
(hierarchy_tree.py) (control_panel.py) (property_panel.py)
      |             |             |
      v             v             v
 QTreeWidget      QWidget     PropertyView (property_view.py)
(Holds HierarchyVM) (Holds ControlVM) | (QWidget)
                                      |
                                      v (Holds PropertyVM)
```

## 类的职责

### 模型层 (`xml_editor.model`)
- `geometry.py`: 定义几何体 (`Geometry`, `GeometryGroup`, `BaseGeometry`)、材质 (`Material`) 及相关枚举 (`GeometryType`, `OperationMode`) 的核心数据结构和基础变换。
- `xml_parser.py`: 处理 MuJoCo XML 文件的加载和保存逻辑。
- `raycaster.py`: 实现从屏幕坐标到3D世界的光线投射，用于对象拾取。

### 视图模型层 (`xml_editor.viewmodel`)
- `scene_viewmodel.py`: 管理整个场景的状态，包括几何体列表、当前选择、摄像机配置、射线投射器实例；处理场景级别操作（加载/保存数据、创建/删除对象、选择）。是多个其他 ViewModel 依赖的核心。
- `property_viewmodel.py`: 管理属性面板的状态，获取和设置当前选中对象的属性，并在属性变化时通知视图。依赖 `SceneViewModel` 获取选择和对象变化。
- `hierarchy_viewmodel.py`: 管理层级树的状态，处理对象的父子关系、分组、复制/粘贴等层级相关操作。依赖 `SceneViewModel` 获取几何体列表和变化。
- `control_viewmodel.py`: 管理控制面板的状态，处理操作模式（平移/旋转/缩放/观察）、坐标系切换以及场景JSON存档的保存和加载逻辑。依赖 `SceneViewModel` 获取和设置操作模式及存档数据。

### 视图层 (`xml_editor.view`)
- `main.py` (`MainWindow`): 主应用窗口，继承自 `QMainWindow`，负责组合所有视图组件（停靠窗口、菜单栏等）和初始化并连接视图模型与视图。
- `opengl_view.py` (`OpenGLView`): 继承自 `QOpenGLWidget`，负责渲染3D场景、绘制Gizmo、处理鼠标/键盘交互以实现场景导航和对象操作，处理拖放创建。持有 `SceneViewModel`。
- `property_panel.py` (`PropertyPanel`) / `property_view.py` (`PropertyView`): 属性面板，显示和编辑选中对象的属性。`PropertyPanel` 是包含 `PropertyView` 的容器。`PropertyView` 持有 `PropertyViewModel`。
- `hierarchy_tree.py` (`HierarchyTree`): 继承自 `QTreeWidget`，显示场景的对象层级，处理层级视图中的选择、右键菜单、拖放操作。持有 `HierarchyViewModel`。
- `control_panel.py` (`ControlPanel`): 操作控制面板，提供工具选择按钮、几何体创建按钮和存档管理按钮。持有 `ControlViewModel`。

## 贡献指南

欢迎对本项目提出建议和贡献代码。请遵循以下步骤：

1. Fork本仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建Pull Request

## 许可

本项目采用MIT许可证，详情请参阅[LICENSE](LICENSE)文件。