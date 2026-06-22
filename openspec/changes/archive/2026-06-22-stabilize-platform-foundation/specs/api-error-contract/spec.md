## ADDED Requirements

### Requirement: API 错误响应具有统一兼容结构
系统 SHALL 为 `/api` 下状态码不小于 400 的响应返回 JSON 错误体，包含字符串 `error`、稳定字符串 `code` 和非空 `request_id`，并允许按需包含对象类型的 `details`。

#### Scenario: 现有客户端错误被归一化
- **WHEN** API 端点返回仅含 `error` 字符串的 400 响应
- **THEN** 系统保留原错误文本并补充 `code` 和 `request_id`

#### Scenario: 资源不存在
- **WHEN** 客户端请求不存在的 API 资源
- **THEN** 系统返回 404 和统一 JSON 错误结构

### Requirement: 服务端异常信息受到保护
系统 MUST 对客户端隐藏未处理异常及现有 5xx 响应中的内部异常文本，并 MUST 在服务端记录包含请求标识和堆栈的异常日志。

#### Scenario: 未处理异常
- **WHEN** API 请求处理期间抛出未处理异常
- **THEN** 系统返回通用 500 错误信息、稳定错误码和请求标识，且日志可通过该请求标识定位异常

#### Scenario: 路由返回内部异常文本
- **WHEN** 现有路由捕获异常并将异常文本放入 5xx 响应
- **THEN** 响应归一化层在发送前用通用错误信息替换内部文本

### Requirement: API 成功响应保持不变
系统 SHALL 仅归一化错误响应，不得改变状态码小于 400 的既有响应体。

#### Scenario: 成功请求
- **WHEN** API 端点返回成功响应
- **THEN** 客户端收到与归一化功能启用前相同的业务响应体和状态码
