import 'dart:async';
import 'dart:convert';
import '../config.dart';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';
import '../widgets/bottom_nav.dart';
import '../providers/image_provider.dart';
import '../providers/theme_provider.dart';
import '../data/themes.dart';
import 'GeneratedPage.dart';

class ThemePage extends StatefulWidget {
  const ThemePage({super.key});

  @override
  State<ThemePage> createState() => _ThemePageState();
}

class _ThemePageState extends State<ThemePage> {
  bool _isGenerating = false;
  String _status = '';
  double _progress = 0; // 0..100, shown as a bar while generating
  Timer? _pollTimer;
  DateTime _stageStart = DateTime.now();
  String _stage = '';
  final TextEditingController _promptController = TextEditingController();

  static const String _baseUrl = apiBaseUrl;

  String _apiThemeName(String title) {
    const map = {
      'Diwali': 'Diwali',
      'Christmas': 'Christmas',
      'Halloween': 'Halloween',
      'Birthday': 'Birthday',
      'Onam': 'onam',
      'Pop-Culture': 'Pop-Culture',
    };
    return map[title] ?? title;
  }

  void _onThemeSelected(String title) {
    final provider = context.read<ThemeProviderModel>();
    if (provider.selectedTheme == title) {
      provider.clear(); // tap again to un-select, e.g. to use only a prompt
    } else {
      provider.setTheme(title, themes[title] ?? '');
    }
  }

  // A design needs a theme, a prompt, or both.
  bool _canContinue(ThemeProviderModel t) =>
      t.selectedTheme != null || _promptController.text.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _promptController.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _handleContinue() async {
    final themeProvider =
        Provider.of<ThemeProviderModel>(context, listen: false);
    final imageProvider =
        Provider.of<ImageProviderModel>(context, listen: false);

    if (!_canContinue(themeProvider)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Pick a theme, describe your room, or both.'),
            behavior: SnackBarBehavior.floating),
      );
      return;
    }

    if (imageProvider.image == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('No image found. Please go back and add a photo.'),
            behavior: SnackBarBehavior.floating),
      );
      return;
    }

    final token =
        Supabase.instance.client.auth.currentSession?.accessToken;
    if (token == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Not logged in.'),
            behavior: SnackBarBehavior.floating),
      );
      return;
    }

    final String? themeName = themeProvider.selectedTheme == null
        ? null
        : _apiThemeName(themeProvider.selectedTheme!);
    final userPrompt = _promptController.text.trim();

    setState(() {
      _isGenerating = true;
      _progress = 0;
      _stage = '';
      _status = 'Checking the AI server...';
    });

    final progressId =
        '${DateTime.now().microsecondsSinceEpoch}${Random().nextInt(99999)}';

    try {
      // Step 0: is the Colab GPU server awake?
      try {
        final st = await http
            .get(Uri.parse('$_baseUrl/api/ai/status'))
            .timeout(const Duration(seconds: 15));
        if (st.statusCode == 200 && jsonDecode(st.body)['online'] != true) {
          throw _AiOfflineException();
        }
      } on _AiOfflineException {
        rethrow;
      } catch (_) {
        // Could not even reach our own backend.
        throw _BackendDownException();
      }

      setState(() => _status = 'Uploading your room photo...');

      // Step 1: Upload room photo
      final uploadRequest = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/api/rooms/'),
      );
      uploadRequest.headers['Authorization'] = 'Bearer $token';
      uploadRequest.fields['room_name'] =
          '${themeProvider.selectedTheme ?? 'Custom'} Room';
      uploadRequest.fields['type'] = 'living_room';
      uploadRequest.files.add(
        // fromBytes (not fromPath) so it also works on Flutter web, where
        // dart:io files do not exist. The backend sniffs the real image type.
        http.MultipartFile.fromBytes(
          'image',
          await imageProvider.image!.readAsBytes(),
          filename: imageProvider.image!.name.isNotEmpty
              ? imageProvider.image!.name
              : 'room.jpg',
        ),
      );

      final uploadResponse = await uploadRequest
          .send()
          .timeout(const Duration(seconds: 30));
      final uploadBody = await uploadResponse.stream.bytesToString();

      if (uploadResponse.statusCode != 201) {
        throw Exception('Upload failed: $uploadBody');
      }
      final room = jsonDecode(uploadBody);
      final roomId = room['room_id'];

      // Step 2: Generate design — 10 min timeout. While it runs, ask the
      // backend which step it is on every 2 seconds.
      setState(() {
        _progress = 8;
        _status = 'Sending your photo to the AI...';
      });
      _startProgressPolling(token, progressId);

      final designResponse = await http
          .post(
            Uri.parse('$_baseUrl/api/designs/generate'),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
              'X-Progress-Id': progressId,
            },
            body: jsonEncode({
              'room_id': roomId,
              'theme_name': themeName,
              'style': null,
              'user_prompt': userPrompt.isNotEmpty ? userPrompt : null,
            }),
          )
          .timeout(const Duration(minutes: 10)); // ✅ 10 min timeout

      _pollTimer?.cancel();

      if (designResponse.statusCode == 503) {
        throw _AiOfflineException();
      }
      if (designResponse.statusCode != 201) {
        throw Exception(_friendlyDetail(designResponse.body));
      }
      final design = jsonDecode(designResponse.body);

      // Step 3: Get bundle
      setState(() {
        _progress = 97;
        _status = 'Building your product bundle...';
      });

      final bundleResponse = await http
          .get(
            Uri.parse(
                '$_baseUrl/api/designs/${design['design_id']}/bundle'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(const Duration(seconds: 30));

      Map<String, dynamic>? bundle;
      if (bundleResponse.statusCode == 200) {
        bundle = jsonDecode(bundleResponse.body);
      }

      // Step 4: Navigate
      if (mounted) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => GeneratedPage(
              design: design,
              bundle: bundle,
              themeName: themeProvider.selectedTheme ?? 'Custom design',
            ),
          ),
        );
      }
    } on _AiOfflineException {
      _pollTimer?.cancel();
      if (mounted) {
        setState(() => _isGenerating = false);
        _showOfflineDialog();
      }
    } on _BackendDownException {
      _pollTimer?.cancel();
      if (mounted) {
        setState(() => _isGenerating = false);
        _showError(
            'Cannot reach the Indar server. Make sure the backend is running and you are online, then try again.');
      }
    } on TimeoutException {
      _pollTimer?.cancel();
      if (mounted) {
        setState(() => _isGenerating = false);
        _showError('This is taking too long. Please try again in a minute.');
      }
    } catch (e) {
      print('Error: $e');
      _pollTimer?.cancel();
      if (mounted) {
        setState(() => _isGenerating = false);
        _showError(e.toString().replaceFirst('Exception: ', ''));
      }
    }
  }

  void _startProgressPolling(String token, String progressId) {
    _pollTimer?.cancel();
    _stageStart = DateTime.now();
    _stage = '';
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final r = await http.get(
          Uri.parse('$_baseUrl/api/designs/progress/$progressId'),
          headers: {'Authorization': 'Bearer $token'},
        ).timeout(const Duration(seconds: 5));
        if (r.statusCode != 200 || !mounted || !_isGenerating) return;
        final j = jsonDecode(r.body);
        final stage = (j['stage'] ?? '') as String;
        if (stage == 'unknown') return;
        if (stage != _stage) {
          _stage = stage;
          _stageStart = DateTime.now();
        }
        final base = (j['percent'] as num).toDouble();
        var pct = base;
        if (stage == 'generating') {
          // The GPU does not report steps, so ease from 30% towards 85%.
          final t = DateTime.now().difference(_stageStart).inSeconds;
          pct = 30 + 55 * (1 - exp(-t / 35));
        }
        setState(() {
          if (pct > _progress) _progress = pct;
          _status = j['message'] as String;
        });
      } catch (_) {
        // A missed poll is fine; the next one will catch up.
      }
    });
  }

  String _friendlyDetail(String body) {
    try {
      final d = jsonDecode(body)['detail'];
      if (d is String && d.isNotEmpty) return d;
    } catch (_) {}
    return 'Something went wrong while generating your design. Please try again.';
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.red.shade800,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 6),
      ),
    );
  }

  void _showOfflineDialog() {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('The AI server is asleep'),
        content: const Text(
          'Your room photo is fine. The free GPU that redecorates it is not running right now.\n\n'
          '1. Open the Indar Colab notebook\n'
          '2. Press Runtime > Run all\n'
          '3. Wait for "Registered with your Indar backend"\n'
          '4. Come back here and tap Try again',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _handleContinue();
            },
            child: const Text('Try again'),
          ),
        ],
      ),
    );
  }

  Widget _buildGeneratingState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _AnimatedRoomBuilder(status: _status),
          const SizedBox(height: 28),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 48),
            child: Column(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: LinearProgressIndicator(
                    value: (_progress / 100).clamp(0.0, 1.0),
                    minHeight: 6,
                    backgroundColor: Colors.black12,
                    color: Colors.black,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '${_progress.round()}%',
                  style: const TextStyle(fontSize: 12, color: Colors.black45),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              _status,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 14, color: Colors.black54, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProviderModel>();

    return Scaffold(
      backgroundColor: const Color(0xfff3f3f3),
      bottomNavigationBar: buildBottomNav(context),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 25),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 20),

              // Header
              Row(
                children: [
                  GestureDetector(
                    onTap: () => Navigator.pop(context),
                    child: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.black12),
                      ),
                      child: const Icon(Icons.arrow_back, size: 18),
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Step 2 of 3',
                          style: TextStyle(
                              fontSize: 12, color: Colors.black45)),
                      Text('Choose a Theme',
                          style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600)),
                    ],
                  ),
                ],
              ),

              const SizedBox(height: 16),

              // Progress bar
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: LinearProgressIndicator(
                  value: 0.66,
                  minHeight: 6,
                  backgroundColor: Colors.grey.shade200,
                  color: Colors.black,
                ),
              ),

              const SizedBox(height: 6),
              Text(
                'Pick a theme, describe your room, or do both',
                style: TextStyle(
                    fontSize: 13,
                    color: Colors.black.withOpacity(0.45)),
              ),

              const SizedBox(height: 20),

              // Theme grid or generating state
              Expanded(
                child: _isGenerating
                    ? _buildGeneratingState()
                    : SingleChildScrollView(
                        child: Column(
                          children: [
                            GridView.count(
                              shrinkWrap: true,
                              physics:
                                  const NeverScrollableScrollPhysics(),
                              crossAxisCount: 2,
                              mainAxisSpacing: 14,
                              crossAxisSpacing: 14,
                              childAspectRatio: 1.1,
                              children: [
                                'Diwali',
                                'Christmas',
                                'Halloween',
                                'Birthday',
                                'Onam',
                                'Pop-Culture',
                              ]
                                  .map((t) => _ThemeCard(
                                        title: t,
                                        isSelected:
                                            themeProvider.selectedTheme ==
                                                t,
                                        onTap: () =>
                                            _onThemeSelected(t),
                                      ))
                                  .toList(),
                            ),

                            // Editable prompt box
                            ...[
                              const SizedBox(height: 16),
                              Container(
                                padding: const EdgeInsets.all(14),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius:
                                      BorderRadius.circular(14),
                                  border:
                                      Border.all(color: Colors.black12),
                                ),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Container(
                                          width: 28,
                                          height: 28,
                                          decoration: BoxDecoration(
                                            color: Colors.black,
                                            borderRadius:
                                                BorderRadius.circular(
                                                    8),
                                          ),
                                          child: const Icon(
                                              Icons.edit_outlined,
                                              color: Colors.white,
                                              size: 14),
                                        ),
                                        const SizedBox(width: 10),
                                        const Text(
                                            'Describe your room (optional)',
                                            style: TextStyle(
                                                fontSize: 13,
                                                fontWeight:
                                                    FontWeight.w600)),
                                        const Spacer(),
                                        GestureDetector(
                                          onTap: () => _promptController.clear(),
                                          child: Text(
                                            'Clear',
                                            style: TextStyle(
                                                fontSize: 11,
                                                color: Colors.black
                                                    .withOpacity(0.4)),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 10),
                                    TextField(
                                      controller: _promptController,
                                      maxLines: 4,
                                      style: const TextStyle(
                                          fontSize: 13, height: 1.5),
                                      decoration: InputDecoration(
                                        hintText:
                                            'e.g. a cozy reading corner with plants, a sofa and warm lights...',
                                        hintStyle: TextStyle(
                                            fontSize: 12,
                                            color: Colors.black
                                                .withOpacity(0.3)),
                                        filled: true,
                                        fillColor:
                                            const Color(0xFFF8F8F8),
                                        border: OutlineInputBorder(
                                          borderRadius:
                                              BorderRadius.circular(10),
                                          borderSide: BorderSide.none,
                                        ),
                                        contentPadding:
                                            const EdgeInsets.all(12),
                                      ),
                                    ),
                                    const SizedBox(height: 6),
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 6,
                                      children: [
                                        'More lights',
                                        'Sofa and rug',
                                        'Lots of plants',
                                        'Modern and minimal',
                                      ]
                                          .map((t) => ActionChip(
                                                label: Text(t,
                                                    style: const TextStyle(
                                                        fontSize: 11)),
                                                backgroundColor:
                                                    const Color(0xFFF1F1F1),
                                                side: BorderSide.none,
                                                onPressed: () {
                                                  final cur =
                                                      _promptController.text
                                                          .trim();
                                                  _promptController.text =
                                                      cur.isEmpty
                                                          ? t
                                                          : '$cur, $t';
                                                },
                                              ))
                                          .toList(),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      'Theme only: we decorate it for you. Prompt only: we follow your words. Both: your words adjust the theme.',
                                      style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.black
                                              .withOpacity(0.35)),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 16),
                            ],
                          ],
                        ),
                      ),
              ),

              const SizedBox(height: 14),

              // Continue button
              GestureDetector(
                onTap: _isGenerating ? null : _handleContinue,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  height: 55,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: _isGenerating || !_canContinue(themeProvider)
                        ? Colors.grey.shade300
                        : Colors.black,
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Center(
                    child: Text(
                      _isGenerating ? 'Generating...' : 'Continue',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: _isGenerating || !_canContinue(themeProvider)
                            ? Colors.black38
                            : Colors.white,
                      ),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 20),
            ],
          ),
        ),
      ),
    );
  }
} // ← _ThemePageState ends here

// ── Theme Card ─────────────────────────────────────────────────
class _ThemeCard extends StatelessWidget {
  final String title;
  final bool isSelected;
  final VoidCallback onTap;

  const _ThemeCard({
    required this.title,
    required this.isSelected,
    required this.onTap,
  });

  static String _imageForTheme(String title) {
    const map = {
      'Halloween': 'assets/images/Halloween.jpg',
      'Christmas': 'assets/images/Christmas.jpg',
      'Diwali': 'assets/images/Diwali.jpg',
      'Onam': 'assets/images/Onam.jpg',
      'Birthday': 'assets/images/Bday.jpg',
      'Pop-Culture': 'assets/images/pop.jpg',
      'Party': 'assets/images/Bday.jpg',
    };
    return map[title] ?? 'assets/images/room.jpg';
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? Colors.black : Colors.transparent,
            width: 3,
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(13),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Image.asset(_imageForTheme(title), fit: BoxFit.cover),
              Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      Colors.black
                          .withOpacity(isSelected ? 0.75 : 0.5),
                    ],
                  ),
                ),
              ),
              Positioned(
                bottom: 10,
                left: 10,
                right: 10,
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 14),
                      ),
                    ),
                    if (isSelected)
                      Container(
                        width: 22,
                        height: 22,
                        decoration: const BoxDecoration(
                            color: Colors.white,
                            shape: BoxShape.circle),
                        child: const Icon(Icons.check,
                            color: Colors.black, size: 14),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Animated Room Builder ──────────────────────────────────────
class _AnimatedRoomBuilder extends StatefulWidget {
  final String status;
  const _AnimatedRoomBuilder({required this.status});

  @override
  State<_AnimatedRoomBuilder> createState() =>
      _AnimatedRoomBuilderState();
}

class _AnimatedRoomBuilderState extends State<_AnimatedRoomBuilder>
    with TickerProviderStateMixin {
  late AnimationController _floatController;
  late AnimationController _pulseController;
  late AnimationController _orbitController;
  late AnimationController _shimmerController;
  late AnimationController _msgFadeController;

  late Animation<double> _floatAnim;
  late Animation<double> _pulseAnim;
  late Animation<double> _orbitAnim;
  late Animation<double> _shimmerAnim;
  late Animation<double> _msgFadeAnim;

  final List<String> _funMessages = [
    'Teaching AI about feng shui... 🪴',
    'Arguing with the AI about curtain colors... 🎨',
    'Measuring your virtual walls... 📐',
    'Summoning the decoration spirits... ✨',
    'Consulting the interior design oracle... 🔮',
    'Placing imaginary furniture... 🛋️',
    'Mixing festive paint colors... 🖌️',
    'The AI is having a creative moment... 💡',
    'Untangling the fairy lights... 💫',
    'Polishing the virtual diyas... 🪔',
  ];

  int _messageIndex = 0;

  @override
  void initState() {
    super.initState();

    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    _orbitController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4000),
    )..repeat();

    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat();

    _msgFadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    )..value = 1.0;

    _floatAnim = Tween<double>(begin: -8, end: 8).animate(
      CurvedAnimation(parent: _floatController, curve: Curves.easeInOut),
    );

    _pulseAnim = Tween<double>(begin: 0.92, end: 1.08).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _orbitAnim = Tween<double>(begin: 0, end: 2 * pi).animate(
      CurvedAnimation(parent: _orbitController, curve: Curves.linear),
    );

    _shimmerAnim = Tween<double>(begin: -1, end: 2).animate(
      CurvedAnimation(
          parent: _shimmerController, curve: Curves.easeInOut),
    );

    _msgFadeAnim = CurvedAnimation(
      parent: _msgFadeController,
      curve: Curves.easeInOut,
    );

    _startMessageCycle();
  }

  void _startMessageCycle() async {
    while (mounted) {
      await Future.delayed(const Duration(seconds: 3));
      if (!mounted) break;
      await _msgFadeController.reverse();
      if (!mounted) break;
      setState(() {
        _messageIndex = (_messageIndex + 1) % _funMessages.length;
      });
      await _msgFadeController.forward();
    }
  }

  @override
  void dispose() {
    _floatController.dispose();
    _pulseController.dispose();
    _orbitController.dispose();
    _shimmerController.dispose();
    _msgFadeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 200,
          height: 200,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Outer pulsing ring
              AnimatedBuilder(
                animation: _pulseAnim,
                builder: (_, __) => Transform.scale(
                  scale: _pulseAnim.value,
                  child: Container(
                    width: 160,
                    height: 160,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.black.withOpacity(0.06),
                        width: 2,
                      ),
                    ),
                  ),
                ),
              ),

              // Second pulsing ring
              AnimatedBuilder(
                animation: _pulseAnim,
                builder: (_, __) => Transform.scale(
                  scale: 1.2 - (_pulseAnim.value - 0.92) * 0.5,
                  child: Container(
                    width: 160,
                    height: 160,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.black.withOpacity(0.04),
                        width: 1.5,
                      ),
                    ),
                  ),
                ),
              ),

              // Orbiting dots
              AnimatedBuilder(
                animation: _orbitAnim,
                builder: (_, __) => Stack(
                  alignment: Alignment.center,
                  children: List.generate(4, (i) {
                    final angle = _orbitAnim.value + (i * pi / 2);
                    const radius = 72.0;
                    return Transform.translate(
                      offset: Offset(
                        cos(angle) * radius,
                        sin(angle) * radius,
                      ),
                      child: Container(
                        width: i % 2 == 0 ? 8 : 6,
                        height: i % 2 == 0 ? 8 : 6,
                        decoration: BoxDecoration(
                          color: Colors.black
                              .withOpacity(i % 2 == 0 ? 0.7 : 0.3),
                          shape: BoxShape.circle,
                        ),
                      ),
                    );
                  }),
                ),
              ),

              // Center floating card with shimmer
              AnimatedBuilder(
                animation: Listenable.merge(
                    [_floatAnim, _shimmerAnim, _pulseAnim]),
                builder: (_, __) => Transform.translate(
                  offset: Offset(0, _floatAnim.value),
                  child: Container(
                    width: 100,
                    height: 100,
                    decoration: BoxDecoration(
                      color: Colors.black,
                      borderRadius: BorderRadius.circular(28),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.15),
                          blurRadius: 20,
                          offset:
                              Offset(0, _floatAnim.value * 0.5 + 8),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(28),
                      child: Stack(
                        children: [
                          Positioned.fill(
                            child: AnimatedBuilder(
                              animation: _shimmerAnim,
                              builder: (_, __) => Transform.translate(
                                offset: Offset(
                                    _shimmerAnim.value * 120, 0),
                                child: Container(
                                  width: 40,
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      colors: [
                                        Colors.white.withOpacity(0),
                                        Colors.white
                                            .withOpacity(0.08),
                                        Colors.white.withOpacity(0),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const Center(
                            child: Icon(Icons.auto_awesome,
                                color: Colors.white, size: 44),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              // Counter-orbiting sparkles
              AnimatedBuilder(
                animation: _orbitAnim,
                builder: (_, __) => Stack(
                  alignment: Alignment.center,
                  children: List.generate(3, (i) {
                    final angle =
                        -_orbitAnim.value * 0.7 + (i * 2 * pi / 3);
                    const radius = 46.0;
                    return Transform.translate(
                      offset: Offset(
                        cos(angle) * radius,
                        sin(angle) * radius,
                      ),
                      child: Icon(
                        Icons.star,
                        size: i == 0 ? 10 : 7,
                        color: Colors.black
                            .withOpacity(i == 0 ? 0.5 : 0.25),
                      ),
                    );
                  }),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),

        // Fun message pill
        FadeTransition(
          opacity: _msgFadeAnim,
          child: Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.black12),
            ),
            child: Text(
              _funMessages[_messageIndex],
              style: const TextStyle(
                fontSize: 13,
                color: Colors.black54,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _AiOfflineException implements Exception {}

class _BackendDownException implements Exception {}
