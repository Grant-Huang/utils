## 它能做什么

一个工具：`convert_to_markdown(uri)`，把文档转成 Markdown。上游是微软的 MarkItDown。

## 实测结果

- **Word / PowerPoint / Excel / HTML**：能转，**中文保留**，表格转成 Markdown 表格。我们用 office 服务生成的 docx、pptx、xlsx 做了读回测试，都成功。
- **图片：返回空内容，没有 OCR**（用一张写有文字的 PNG 实测）。需要识别图片文字的场景，这个服务做不到。
- ZIP、PDF：**未实测**。

## 怎么传文件

`uri` 接受 `data:` URI。远程服务读不到你本机的路径，所以把文件 base64 编码，用 `data:<mime>;base64,<内容>` 传入。

## 安全（必读）

上游明确说明：**不支持鉴权，并且 `convert_to_markdown` 能读服务器上的任意文件、访问任意网络地址**。我们实测了：`file:///etc/hostname` 直接返回了文件内容。
另外，一个让它访问自身端口的请求会把它的事件循环卡死，之后普通 SIGTERM 都杀不掉。

所以部署时：放在 `internal` 网络（无外网出口）、容器里不放任何密钥、入口由网关统一鉴权，并且**不要把它开放给不受信任的调用方**。
调用时请只使用 `data:` URI，不要传 `file://` 或内网地址。

## 版本

PyPI 上目前只有 alpha 版（`0.0.1a7`），镜像里钉死了版本。

## 相关

配套 Skill：`skill-read-attachments`。
