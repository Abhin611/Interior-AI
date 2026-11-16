import 'dart:js_interop';
import 'dart:typed_data';
import 'package:web/web.dart' as web;

/// Triggers a normal browser download of [bytes] named [filename].
Future<void> downloadBytes(Uint8List bytes, String filename, String mime) async {
  final blob = web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: mime));
  final url = web.URL.createObjectURL(blob);
  final a = web.document.createElement('a') as web.HTMLAnchorElement
    ..href = url
    ..download = filename;
  web.document.body!.append(a);
  a.click();
  a.remove();
  web.URL.revokeObjectURL(url);
}
