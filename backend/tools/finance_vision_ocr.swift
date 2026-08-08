import Foundation
import ImageIO
import Vision

struct OCRObservation: Codable {
    let text: String
    let confidence: Float
    let boundingBox: [Double]

    enum CodingKeys: String, CodingKey {
        case text
        case confidence
        case boundingBox = "bounding_box"
    }
}

struct OCRResult: Codable {
    let status: String
    let observations: [OCRObservation]
    let error: String?
}

func emit(_ result: OCRResult, exitCode: Int32 = 0) -> Never {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.withoutEscapingSlashes]
    let data = (try? encoder.encode(result)) ?? Data("{\"status\":\"failed\",\"observations\":[],\"error\":\"encoding failed\"}".utf8)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(exitCode)
}

guard CommandLine.arguments.count == 2 else {
    emit(OCRResult(status: "failed", observations: [], error: "usage: finance-vision-ocr IMAGE"), exitCode: 2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    emit(OCRResult(status: "failed", observations: [], error: "unable to decode image"), exitCode: 3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true

do {
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    let observations = (request.results ?? []).compactMap { observation -> OCRObservation? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return OCRObservation(
            text: candidate.string,
            confidence: candidate.confidence,
            boundingBox: [box.origin.x, box.origin.y, box.size.width, box.size.height]
        )
    }
    emit(OCRResult(status: "success", observations: observations, error: nil))
} catch {
    emit(OCRResult(status: "failed", observations: [], error: String(describing: error)), exitCode: 4)
}
