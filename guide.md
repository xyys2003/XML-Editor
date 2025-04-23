## **LLM Agent项目重构操作指南：PyQt5 MuJoCo场景编辑器**

**版本:** 1.0
**日期:** 2024-08-06

**1. 项目背景与目标**

*   **项目描述:** 这是一个使用Python和PyQt5构建的图形界面编辑器，专门用于创建和编辑MuJoCo场景描述语言（mjcf）文件。
*   **当前状态:** 代码库缺乏依赖管理文件（如 `requirements.txt` 或 `pyproject.toml`）、使用说明、文档，并且可能包含冗余代码和通配符导入 (`import *`)。
*   **重构目标:**
    1.  **代码精简:** 识别并移除未使用的函数、方法、类。
    2.  **依赖清理:** 明确项目依赖，移除未使用依赖，消除 `import *` 用法。
    3.  **现代化打包:** 引入 `pyproject.toml` 进行依赖管理和项目构建（推荐使用 Poetry 或 PDM）。
    4.  **架构升级:** 将项目重构为MVVM（Model-View-ViewModel）架构模式。
    5.  **文档完善:** 添加代码级文档（Docstrings）和项目级文档（README）。

**2. 重构流程与步骤**

**阶段一：项目分析与理解 (Analysis & Understanding)**

*   **目标:** 彻底理解现有代码库的结构、功能、入口点和潜在依赖。
*   **步骤:**
    1.  **文件结构扫描:**
        *   使用 `list_dir` 工具列出项目根目录及各子目录的文件和文件夹。
        *   绘制或描述项目的大致目录结构。
    2.  **入口点识别:**
        *   搜索包含 `if __name__ == "__main__":` 的 `.py` 文件。
        *   查找可能的主执行脚本（例如 `main.py`, `app.py` 等）。
    3.  **初步依赖识别:**
        *   使用 `grep_search` 或 `codebase_search` 查找 `import` 语句。
        *   重点关注 `PyQt5`, `xml.etree.ElementTree` (或其他XML解析库), 以及任何与MuJoCo或mjcf相关的导入。
        *   *注意：由于没有依赖文件，这只是初步估计。*
    4.  **代码结构分析:**
        *   使用 `read_file` 工具阅读关键文件（如识别出的入口点、主要的UI类文件、核心逻辑文件）。
        *   识别主要的类、它们之间的关系、PyQt5窗口和控件的使用方式、事件处理逻辑等。
        *   理解当前数据（mjcf场景信息）是如何被加载、表示、修改和保存的。

**阶段二：依赖管理与导入规范 (Dependency Management & Import Cleanup)**

*   **目标:** 建立标准的依赖管理，清理并规范化模块导入。
*   **步骤:**
    1.  **初始化 `pyproject.toml`:**
        *   建议使用 Poetry。在项目根目录运行 `poetry init`（需要用户确认或Agent执行 `run_terminal_cmd`）。根据提示填写项目信息。
        *   将阶段一识别出的核心依赖（如 `PyQt5`）添加到 `pyproject.toml` 中：`poetry add PyQt5`。
    2.  **替换通配符导入:**
        *   使用 `grep_search` 查找 `import \*` 语句。
        *   分析使用这些通配符导入的模块，确定实际需要导入的具体类、函数或变量。
        *   使用 `edit_file` 工具将 `from module import *` 修改为 `from module import specific_item1, specific_item2`。
    3.  **识别并移除未使用导入:**
        *   (可选，但推荐) 尝试使用静态分析工具如 `vulture`。运行 `poetry add vulture --group dev` 添加到开发依赖，然后运行 `poetry run vulture .`（可能需要 `run_terminal_cmd`）。
        *   或者，在后续的代码精简和重构过程中，手动检查并移除不再需要的 `import` 语句。
    4.  **依赖确认:** 在清理导入后，再次审视 `pyproject.toml`，移除不再需要的依赖项 (`poetry remove package_name`)。

**阶段三：代码精简 (Code Simplification)**

*   **目标:** 移除项目中未被任何地方调用的“死代码”（Dead Code）。
*   **步骤:**
    1.  **死代码分析:**
        *   再次利用 `vulture` (如果已安装) 或进行更细致的 `codebase_search` 和 `grep_search`。
        *   对于每个函数、方法和类，搜索其调用点。如果一个非入口点的公共成员或整个类没有任何调用者，则可能是死代码。
        *   *注意：动态调用或某些框架特性可能导致误判，需谨慎。*
    2.  **安全移除:**
        *   对于确认为死代码的部分，使用 `edit_file` 工具将其注释掉或删除。
        *   进行小范围移除后，尝试运行项目或关键功能，确保没有破坏现有功能。
        *   *建议：优先注释掉，待整个重构稳定后再彻底删除。*

**阶段四：MVVM架构重构 (MVVM Refactoring)**

*   **目标:** 将代码逻辑按Model、View、ViewModel分离。
*   **步骤:**
    1.  **识别/创建 Model:**
        *   **职责:** 封装mjcf场景数据结构（如树状结构、节点属性）以及与数据相关的业务逻辑（加载、保存、验证、修改数据但不涉及UI）。
        *   **操作:** 查找当前处理mjcf数据加载、解析、保存和内部表示的代码。将其提取或重构到独立的 `model` 模块/类中。Model不应依赖PyQt5。
    2.  **识别 View:**
        *   **职责:** 显示UI元素（窗口、按钮、编辑器区域等），将用户操作（点击、输入）传递给ViewModel。
        *   **操作:** 现有的大部分PyQt5控件和窗口布局代码属于View。View应尽量“哑”（Dumb），只负责显示ViewModel提供的数据，并将事件绑定到ViewModel的命令上。
    3.  **创建 ViewModel:**
        *   **职责:** 作为View和Model的桥梁。持有Model的引用。从Model获取数据，处理成View需要的格式（可能需要格式化、转换）。暴露命令（方法）供View绑定，处理用户输入，调用Model更新数据。实现数据变更通知机制（如PyQt的信号/槽）通知View更新。
        *   **操作:**
            *   为主要的窗口或用户交互单元创建对应的ViewModel类。
            *   在ViewModel中添加属性以暴露需要在View中显示或编辑的数据。
            *   在ViewModel中添加方法（命令）来响应View的事件（如按钮点击、文本更改）。这些方法会调用Model的逻辑。
            *   实现数据绑定：当Model数据变化时，ViewModel应能通知View；当View通过ViewModel修改数据时，最终更新到Model。可以利用PyQt的信号和槽机制。
    4.  **重构代码:**
        *   **从View中移除逻辑:** 将原先在UI类（View）中处理数据获取、格式化、用户输入验证、直接操作数据的逻辑，迁移到对应的ViewModel中。
        *   **连接View与ViewModel:** 在View的构造函数或初始化方法中，创建或接收对应的ViewModel实例。将View的控件属性（如`text`, `checked`）绑定到ViewModel的属性，将View的事件（如`clicked`, `textChanged`）连接到ViewModel的命令（方法）。
        *   **连接ViewModel与Model:** ViewModel持有Model实例，通过调用Model的方法来读写数据。

**阶段五：文档完善 (Documentation Enhancement)**

*   **目标:** 为项目添加必要的文档，方便理解和维护。
*   **步骤:**
    1.  **添加Docstrings:**
        *   使用 `edit_file` 为所有公开的类、方法、函数添加文档字符串（Docstrings）。
        *   遵循一种标准格式，如Google Style或NumPy Style。Docstring应解释其功能、参数、返回值和可能引发的异常。
    2.  **创建/更新 `README.md`:**
        *   使用 `edit_file` 创建或修改项目根目录下的 `README.md` 文件。
        *   内容应包括：
            *   项目简介。
            *   如何安装依赖（例如，`poetry install`）。
            *   如何运行项目（启动命令）。
            *   （可选）项目架构概述。
            *   （可选）基本用法示例。
    3.  **(可选) 生成API文档:**
        *   如果需要更正式的文档，可以配置 Sphinx。添加 `sphinx` 及相关主题 (如 `sphinx-rtd-theme`) 到开发依赖 (`poetry add sphinx sphinx-rtd-theme --group dev`)。
        *   配置 `conf.py` 和 `index.rst`，然后运行 `poetry run sphinx-build -b html sourcedir builddir` (可能需要 `run_terminal_cmd`) 来生成HTML文档。

**阶段六：测试与验证 (Testing & Verification)**

*   **目标:** 确保重构后的项目功能正确，且符合预期。
*   **步骤:**
    1.  **运行检查:** 确保在安装依赖 (`poetry install`) 后，项目能够成功启动并运行 (`poetry run python your_entry_point.py`)。
    2.  **功能测试:** 手动测试编辑器的核心功能：
        *   加载mjcf文件。
        *   显示场景结构/内容。
        *   编辑节点/属性。
        *   添加/删除节点。
        *   保存mjcf文件。
        *   所有UI交互是否符合预期。
    3.  **(可选) 单元测试:**
        *   为Model和ViewModel中的关键逻辑编写单元测试（可以使用 `pytest`）。添加 `pytest` 到开发依赖 (`poetry add pytest --group dev`)。
        *   运行 `poetry run pytest` (可能需要 `run_terminal_cmd`)。

**3. 注意事项与建议**

*   **迭代进行:** 不要试图一次性完成所有重构。按阶段进行，每个阶段或大的步骤完成后进行验证。
*   **版本控制:** 强烈建议在开始重构前和每个重要步骤后，使用Git等版本控制系统进行提交，以便于回滚。Agent可能需要提示用户进行此操作。
*   **谨慎删除:** 在确认代码无用前，优先注释而非直接删除。
*   **沟通:** 在重构过程中，Agent可能需要向用户确认某些逻辑、依赖或代码片段的用途。
*   **错误处理:** 确保重构过程中考虑到并适当处理了文件I/O、数据解析等环节的潜在错误。

---

请Agent按照此指南逐步执行重构任务。在每个阶段开始前，明确告知用户当前目标和主要步骤。在遇到歧义或需要决策时，与用户沟通。
