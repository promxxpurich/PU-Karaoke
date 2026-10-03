// kara_ocr.swift — อ่านตัวหนังสือในภาพด้วย Apple Vision (รองรับไทย th-TH) สำหรับ scripts/ocr_lyrics.py
// คอมไพล์ครั้งแรกอัตโนมัติ: swiftc -O kara_ocr.swift -o .cache/bin/kara_ocr
// ใช้งาน: kara_ocr <ภาพ1> <ภาพ2> ...   -> stdout บรรทัดละ JSON {"f": ชื่อไฟล์, "t": [[ข้อความ, ความมั่นใจ, x, y, w, h], ...]}
// พิกัดเป็นสัดส่วน 0-1 (y นับจากล่าง ตามแบบ Vision)
import Foundation
import Vision
import AppKit

func recognize(_ path: String) -> [[Any]] {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
    var out: [[Any]] = []
    let req = VNRecognizeTextRequest { r, _ in
        for case let o as VNRecognizedTextObservation in (r.results ?? []) {
            guard let c = o.topCandidates(1).first else { continue }
            let b = o.boundingBox
            out.append([c.string, Double(c.confidence), Double(b.origin.x), Double(b.origin.y),
                        Double(b.size.width), Double(b.size.height)])
        }
    }
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false          // เนื้อเพลงไม่ใช่ภาษาเขียน แก้คำให้ทีไรผิดทุกที
    req.recognitionLanguages = ["th-TH", "en-US"]
    req.minimumTextHeight = 0.025               // ข้ามตัวเล็กจิ๋ว (เครดิต/ลายน้ำ)
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    return out
}

for path in CommandLine.arguments.dropFirst() {
    let items = recognize(path)
    let obj: [String: Any] = ["f": (path as NSString).lastPathComponent, "t": items]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: data, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}
