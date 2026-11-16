import 'dart:typed_data';

Future<void> downloadBytes(Uint8List bytes, String filename, String mime) async {
  throw UnsupportedError('Browser download is only available on the web.');
}
