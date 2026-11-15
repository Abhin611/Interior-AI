import 'package:flutter_test/flutter_test.dart';

import 'package:indar_app/config.dart';
import 'package:indar_app/data/themes.dart';

void main() {
  test('API base URL defaults to the Android emulator host', () {
    // Overridable with --dart-define=API_BASE_URL=...
    expect(apiBaseUrl, startsWith('http'));
    expect(apiBaseUrl, endsWith(':8000'));
  });

  test('theme data is defined', () {
    expect(themes, isNotEmpty);
  });
}
