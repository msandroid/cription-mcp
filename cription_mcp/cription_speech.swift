// cription-speech — on-device transcription with Apple SpeechAnalyzer (macOS 26+).
//
// The same engine Cription uses for its best-scoring languages (e.g. Japanese).
// Audio never leaves the Mac. The MCP server compiles this file on first use.
//
// usage:
//   cription-speech transcribe <audio-or-video-file> [--locale ja-JP] [--terms <file>]
//   cription-speech locales
//
// Output is always one JSON object on stdout; errors go to stderr with exit 1.

import AVFoundation
import Foundation
import Speech

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

func printJSON(_ object: Any) {
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
          let text = String(data: data, encoding: .utf8) else { fail("could not encode output") }
    print(text)
}

/// AVAudioFile reads wav/m4a/mp3/aiff/caf. For video or other containers, decode the
/// first audio track to a temporary 16 kHz mono CAF with AVAssetReader.
func openAudio(_ url: URL) async throws -> (AVAudioFile, URL?) {
    if let file = try? AVAudioFile(forReading: url) { return (file, nil) }

    let asset = AVURLAsset(url: url)
    guard let track = try await asset.loadTracks(withMediaType: .audio).first else {
        throw NSError(domain: "cription-speech", code: 1, userInfo: [NSLocalizedDescriptionKey: "no audio track in \(url.lastPathComponent)"])
    }
    let settings: [String: Any] = [
        AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000, AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsNonInterleaved: false,
    ]
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: settings)
    reader.add(output)
    guard reader.startReading() else { throw reader.error ?? NSError(domain: "cription-speech", code: 2) }

    let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16_000, channels: 1, interleaved: false)!
    let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("cription-\(UUID().uuidString).caf")
    let outFile = try AVAudioFile(forWriting: tempURL, settings: format.settings)
    while let sample = output.copyNextSampleBuffer() {
        guard let block = CMSampleBufferGetDataBuffer(sample) else { continue }
        let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sample))
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { continue }
        buffer.frameLength = frames
        var length = 0
        var pointer: UnsafeMutablePointer<CChar>?
        CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &pointer)
        if let pointer { memcpy(buffer.floatChannelData![0], pointer, min(length, Int(frames) * 4)) }
        try outFile.write(from: buffer)
    }
    if reader.status == .failed { throw reader.error ?? NSError(domain: "cription-speech", code: 3) }
    return (try AVAudioFile(forReading: tempURL), tempURL)
}

func transcribe(path: String, localeID: String?, termsPath: String?) async {
    let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
    guard FileManager.default.fileExists(atPath: url.path) else { fail("file not found: \(url.path)") }

    let requested = localeID.map { Locale(identifier: $0) } ?? Locale.current
    guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: requested) else {
        fail("SpeechTranscriber does not support locale \(requested.identifier); run `cription-speech locales`")
    }
    var terms: [String] = []
    if let termsPath {
        guard let list = try? String(contentsOfFile: termsPath, encoding: .utf8) else { fail("cannot read terms file \(termsPath)") }
        terms = list.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    let transcriber = SpeechTranscriber(locale: locale, transcriptionOptions: [], reportingOptions: [],
                                        attributeOptions: [.audioTimeRange])
    var tempURL: URL?
    defer { if let tempURL { try? FileManager.default.removeItem(at: tempURL) } }
    do {
        if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            let installed = await SpeechTranscriber.installedLocales.map(\.identifier)
            if !installed.contains(locale.identifier) {
                FileHandle.standardError.write(Data("Downloading Apple speech assets for \(locale.identifier)...\n".utf8))
            }
            try await request.downloadAndInstall()
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        if !terms.isEmpty {
            let context = AnalysisContext()
            context.contextualStrings[.general] = terms
            try await analyzer.setContext(context)
        }
        let (audioFile, temp) = try await openAudio(url)
        tempURL = temp
        let duration = Double(audioFile.length) / audioFile.processingFormat.sampleRate

        let collector = Task { () -> [[String: Any]] in
            var segments: [[String: Any]] = []
            for try await result in transcriber.results {
                let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { continue }
                segments.append(["start": result.range.start.seconds, "end": result.range.end.seconds, "text": text])
            }
            return segments
        }
        let started = Date()
        if let last = try await analyzer.analyzeSequence(from: audioFile) {
            try await analyzer.finalizeAndFinish(through: last)
        } else {
            await analyzer.cancelAndFinishNow()
        }
        let segments = try await collector.value
        let joiner = ["ja", "zh", "yue", "th", "ko"].contains(locale.language.languageCode?.identifier ?? "") ? "" : " "
        printJSON([
            "engine": "apple-speechanalyzer",
            "locale": locale.identifier,
            "duration": duration,
            "elapsed": Date().timeIntervalSince(started),
            "segments": segments,
            "text": segments.compactMap { $0["text"] as? String }.joined(separator: joiner),
        ])
    } catch {
        fail("transcription failed: \(error.localizedDescription)")
    }
}

func listLocales() async {
    let supported = await SpeechTranscriber.supportedLocales.map(\.identifier).sorted()
    let installed = Set(await SpeechTranscriber.installedLocales.map(\.identifier))
    printJSON(["supported": supported, "installed": supported.filter { installed.contains($0) }])
}

var args = Array(CommandLine.arguments.dropFirst())
func option(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    let value = args[i + 1]
    args.removeSubrange(i...i + 1)
    return value
}

switch args.first {
case "transcribe":
    let locale = option("--locale")
    let terms = option("--terms")
    guard args.count >= 2 else { fail("usage: cription-speech transcribe <file> [--locale ja-JP] [--terms <file>]") }
    await transcribe(path: args[1], localeID: locale, termsPath: terms)
case "locales":
    await listLocales()
default:
    fail("usage: cription-speech transcribe <file> [--locale id] [--terms file] | cription-speech locales")
}
