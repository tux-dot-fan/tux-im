# tux-im 错误日志

---

## 2026-06-22 — `self._config` vs 模块级 `_config`（Runtime AttributeError）

**位置**: `engine.py` `commit_first()` 和 `select_candidate()`  
**错误**:
```
AttributeError: 'TuxEngine' object has no attribute '_config'
```
**原因**: `TuxEngine.__init__` 从未把 `_config` 存到 `self._config`。代码里写的是模块级 `_config`（OK），但漏写了一句 `self._config = _config`。然而 `commit_first` 和 `select_candidate` 里误写了 `self._config.dictionary.learn_enabled`，实际应该是 `_config.dictionary.learn_enabled`（模块级）。  
**修复**: 
- `self._config` → `_config`（模块级）
- 加 `_config and` 守卫防止 None
- `GooglePinyinMode` 返回值加 `# type: ignore[union-attr,return-value]`
**状态**: ✅ 已修复（mypy --strict 27个文件全部通过）

---

## 2026-06-22 — `PreeditFocusMode.PREEDIT` 不存在

**位置**: `engine.py:405`  
**错误**:
```
AttributeError: type object 'PreeditFocusMode' has no attribute 'PREEDIT'
```
**原因**: IBus 的 `PreeditFocusMode` 枚举只有 `CLEAR` 和 `COMMIT`，没有 `PREEDIT`。  
**修复**: 使用 `PreeditFocusMode.CLEAR`（清除 preedit，不触发自动 commit）。  
**状态**: ✅ 已修复 commit 163d6a7

---

## 2026-06-22 — `append_text` 方法不存在

**位置**: `engine.py:436`  
**错误**:
```
AttributeError: 'Text' object has no attribute 'append_text'
```
**原因**: `IBus.Text` 没有 `append_text` 方法。  
**修复**: `append_text` → `append`  
**状态**: ✅ 已修复（后发现 `append` 也不存在，见下一条）

---

## 2026-06-22 — `IBus.Text.append` 也不存在

**位置**: `engine.py:436`  
**错误**:
```
AttributeError: 'Text' object has no attribute 'append'
```
**原因**: `IBus.Text` 没有 `append` 方法，文本只能一次性创建。  
**修复**: 改用 `IBus.Text.new_from_string()` 创建完整字符串，再用 `set_attributes()` 设置样式。正确流程：

```python
full_text = f"{display}\t{c.comment}"
text = IBus.Text.new_from_string(full_text)
attr = IBus.attr_foreground_new(self._COMMENT_COLOR, len(display), len(full_text))
attr_list = IBus.AttrList.new()
attr_list.append(attr)
text.set_attributes(attr_list)
```
**状态**: ✅ 已修复

---

## 2026-06-22 — `GLib.File` 不存在

**位置**: `main.py:102`  
**错误**:
```
AttributeError: 'gi.repository.GLib' object has no attribute 'file_new_for_path'
```
**原因**: `GLib` 模块没有 `File` 类。需要用 `Gio.File`。  
**修复**: `GLib.file_new_for_path` → `Gio.File.new_for_path`  
**状态**: ✅ 已修复 commit 163d6a7

---

## 2026-06-22 — `monitor_file()` 参数数错误

**位置**: `main.py:103`  
**错误**: `Gio.File.monitor_file() takes exactly 3 arguments (4 given)`  
**原因**: `monitor_file(priority, callback, user_data)` 是错误签名。正确签名是 `(type, flags, cancellable)`，回调不能用 inline 参数传。  
**修复**:
```python
monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
monitor.connect("changed", callback)
```
**状态**: ✅ 已修复 commit 163d6a7

---

## 2026-06-22 — `pyproject.toml` 缺少 lexicon 子包

**位置**: `pyproject.toml`  
**错误**: 打包后 `tux_im.input.lexicon` 未被包含，导致 import 失败  
**修复**: 在 `packages` 列表中添加 `"tux_im.input.lexicon"`  
**状态**: ✅ 已修复 commit 71268ca

---

## 2026-06-22 — `append_attribute` API 参数类型不匹配

**位置**: `engine.py` `_build_lookup()`  
**错误**: `text.append_attribute(IBus.AttrType.FOREGROUND, 0x808080, start, end)` — 参数签名是 `(type, value, start_index, end_index)` 但传入的 `AttrType` 不是 int 类型导致 crash  
**修复**: 用 `IBus.attr_foreground_new(color, start, end)` 创建 attribute，再用 `AttrList.append()` + `text.set_attributes()`  
**状态**: ✅ 已修复

---

## 2026-06-22 — Google Pinyin 模式未注册

**位置**: `engine.py` `ENGINES_BY_MODE`  
**症状**: Google Pinyin 从未激活，走的是普通 Trie-based PinyinMode  
**原因**: `GooglePinyinMode` 未加入 `ENGINES_BY_MODE`，无法通过引擎加载  
**修复**: 
- 注册为 `"google": GooglePinyinMode`
- 添加 `GooglePinyinMode` 的 `_make_mode` 分支
- indicator 缩略图加 `"google": "G"`
- GooglePinyinMode 内部 `name = "pinyin"`（与普通拼音同名，但注册 key 不同所以不冲突）
**状态**: ✅ 已修复

---

## 2026-06-22 — 双字上屏（每个字上屏两个）

**位置**: `engine.py` — `commit_first()` + `_refresh_preedit()`  
**症状**: 按空格选第一个候选时，每个汉字上屏两次  
**原因**: `PreeditFocusMode.COMMIT` 模式下，`_refresh_preedit()` 调用 `update_preedit_text_with_mode()` 会触发 IBus panel 自动 commit preedit。如果此时 panel 也收到了 `commit_text` 信号（或在同一批次事件中重复处理），就会双份。  
**修复**:
1. `_refresh_preedit` 中的 `PreeditFocusMode.COMMIT` → `CLEAR`（不清空 buffer 状态，但避免 panel 自动 commit）
2. `commit_first` 在 `reset()` 后不再调用 `_refresh_preedit()`，改为直接 `hide_preedit_text() + hide_auxiliary_text() + hide_lookup_table()`
**状态**: 🔁 验证中

---

## 2026-06-22 — `do_process_key_event` 未捕获异常crash

**位置**: `engine.py:342/346`  
**错误**:
```
File "...engine.py", line 346, in do_process_key_event
    return self._handle_key(keyval, state)
File "...engine.py", line 377, in _handle_key
    self._refresh_preedit()
File "...engine.py", line 411, in _refresh_preedit
    self.update_lookup_table(self._build_lookup(cands), True)
File "...engine.py", line 427, in _build_lookup
    text.append(comment_str)
AttributeError: 'Text' object has no attribute 'append'
```
**原因**: `_build_lookup` 中 `text.append()` 调用了不存在的方法，导致异常向上穿透 `do_process_key_event` 的外层 try/except  
**修复**: 在 `do_process_key_event` 的 except 块中外层捕获，防止异常泄漏 kill daemon  
**状态**: ✅ 已修复（但根本原因是 `_build_lookup` 的方法调用错误，已一并修复）

---

## 待确认 — 4个 GLib 相关的 AttributeError

**位置**: `main.py` + `engine.py`  
**错误**:
```
File "...main.py", line 102, in main
    gfile = GLib.file_new_for_path(str(config.path))
AttributeError: 'gi.repository.GLib' object has no attribute 'file_new_for_path'
```
此错误阻止了 ibus 引擎正常启动。需要确认 `Gio.File` 是否在所有环境都可用。  
**状态**: ✅ 已修复

---

## 待确认 — ASR overlay bug

**位置**: `tux_im/asr/`  
**问题**: 主线程耦合，未修复  
**状态**: ⏳ 未处理

---

## 已废弃 — emoji 外部词典文件支持

**问题**: EmojiMode 只支持内置 emoji 词典，不支持从外部文件加载  
**状态**: ⏳ 未处理

---

## 已废弃 — LatinMode space 直接透传

**问题**: 拉丁模式下 space 键直接通过，未测试  
**状态**: ⏳ 未处理
