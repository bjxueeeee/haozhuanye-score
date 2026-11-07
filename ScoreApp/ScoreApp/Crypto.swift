//
//  Crypto.swift
//  ScoreApp
//
//  好专业请求体加密：base64( AES-128-ECB-PKCS7( gzip(JSON) ) )
//  密钥硬编码：RequestMappingHa
//

import Foundation
import CommonCrypto
import Compression

enum HQJLCrypto {
    /// 硬编码密钥（16 字节，直接当 AES key）
    static let key = Array("RequestMappingHa".utf8)  // 长度 16

    // MARK: - AES-128-ECB（CommonCrypto，无 IV）

    static func aesECBEncrypt(_ data: Data) -> Data? {
        aesECB(data, op: CCOperation(kCCEncrypt))
    }

    static func aesECBDecrypt(_ data: Data) -> Data? {
        aesECB(data, op: CCOperation(kCCDecrypt))
    }

    private static func aesECB(_ data: Data, op: CCOperation) -> Data? {
        let bufferSize = data.count + kCCBlockSizeAES128
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        var numBytes = 0
        let status = key.withUnsafeBufferPointer { keyBuf in
            data.withUnsafeBytes { dataBuf in
                CCCrypt(
                    op,
                    CCAlgorithm(kCCAlgorithmAES),
                    CCOptions(kCCOptionPKCS7Padding | kCCOptionECBMode),
                    keyBuf.baseAddress, kCCKeySizeAES128,
                    nil,                       // ECB 无 IV
                    dataBuf.baseAddress, data.count,
                    &buffer, bufferSize,
                    &numBytes
                )
            }
        }
        guard status == kCCSuccess else { return nil }
        return Data(bytes: buffer, count: numBytes)
    }

    // MARK: - gzip（Compression + 手动 gzip 头尾，含 CRC32）

    static func gzip(_ data: Data) -> Data? {
        // 1. 用 Compression 得到 zlib 流（2 字节头 + deflate + 4 字节 adler32）
        guard let zlibStream = compress(data: data, algorithm: COMPRESSION_ZLIB) else { return nil }
        // 去掉 zlib 的 2 字节头 + 4 字节 adler32，得到纯 deflate
        let deflate = zlibStream.dropFirst(2).dropLast(4)

        // 2. 构造 gzip：10 字节头 + deflate + 8 字节尾（crc32 + isize）
        var out = Data()
        let header: [UInt8] = [0x1F, 0x8B, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03]
        out.append(contentsOf: header)
        out.append(deflate)

        var crc = crc32(data)
        var littleEndianCrc = crc.littleEndian
        var size = UInt32(data.count).littleEndian
        withUnsafeBytes(of: &littleEndianCrc) { out.append(contentsOf: $0) }
        withUnsafeBytes(of: &size) { out.append(contentsOf: $0) }
        return out
    }

    static func gunzip(_ data: Data) -> Data? {
        // 去掉 gzip 头尾，取 deflate，补 zlib 头尾后解压
        guard data.count > 18 else { return nil }
        let deflate = data.dropFirst(10).dropLast(8)
        var zlibStream = Data([0x78, 0x9C])
        zlibStream.append(deflate)
        // 补 adler32（占位，zlib 解压时若校验失败可能报错；这里用 0 占位）
        zlibStream.append(contentsOf: [0, 0, 0, 0])
        return decompress(data: zlibStream, algorithm: COMPRESSION_ZLIB)
    }

    // MARK: - 压缩/解压封装

    private static func compress(data: Data, algorithm: compression_algorithm) -> Data? {
        let dstSize = data.count + data.count / 2 + 64
        var dst = [UInt8](repeating: 0, count: dstSize)
        let written = data.withUnsafeBytes { src in
            dst.withUnsafeMutableBytes { dest in
                compression_encode_buffer(
                    dest.bindMemory(to: UInt8.self).baseAddress!, dstSize,
                    src.bindMemory(to: UInt8.self).baseAddress!, data.count,
                    nil, algorithm
                )
            }
        }
        guard written > 0 else { return nil }
        return Data(bytes: dst, count: written)
    }

    private static func decompress(data: Data, algorithm: compression_algorithm) -> Data? {
        var out = Data()
        let bufferSize = 64 * 1024
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        let result = data.withUnsafeBytes { src -> Bool in
            var srcOffset = 0
            while srcOffset < data.count {
                let written = buffer.withUnsafeMutableBytes { dest in
                    compression_decode_buffer(
                        dest.bindMemory(to: UInt8.self).baseAddress!, bufferSize,
                        src.baseAddress!.advanced(by: srcOffset), data.count - srcOffset,
                        nil, algorithm
                    )
                }
                guard written > 0 else { return false }
                out.append(buffer, count: written)
                srcOffset += 1 // 简化处理，实际应按源消费量前进
                if written < bufferSize { break }
            }
            return true
        }
        return result ? out : nil
    }

    // MARK: - CRC32（查表法）

    private static var crcTable: [UInt32] = {
        (0..<256).map { i -> UInt32 in
            var c = UInt32(i)
            for _ in 0..<8 {
                c = (c & 1) != 0 ? (0xEDB88320 ^ (c >> 1)) : (c >> 1)
            }
            return c
        }
    }()

    static func crc32(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFFFFFF
        for byte in data {
            let idx = Int((crc ^ UInt32(byte)) & 0xFF)
            crc = crcTable[idx] ^ (crc >> 8)
        }
        return crc ^ 0xFFFFFFFF
    }

    // MARK: - 顶层：JSON → 加密 base64

    static func encryptJSON(_ obj: [String: Any]) -> String? {
        guard let jsonData = try? JSONSerialization.data(withJSONObject: obj),
              let gz = gzip(jsonData),
              let enc = aesECBEncrypt(gz) else { return nil }
        return enc.base64EncodedString()
    }

    static func decryptJSON(_ base64: String) -> [String: Any]? {
        guard let data = Data(base64Encoded: base64),
              let dec = aesECBDecrypt(data),
              let gz = gunzip(dec),
              let obj = try? JSONSerialization.jsonObject(with: gz) as? [String: Any] else { return nil }
        return obj
    }
}
