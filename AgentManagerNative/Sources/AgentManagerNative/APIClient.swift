import Foundation

struct APIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct APIClient {
    let baseURL: URL

    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }

    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await request(path, method: "GET", query: query, body: nil)
    }

    func post<T: Decodable>(_ path: String) async throws -> T {
        try await request(path, method: "POST", query: [], body: Data("{}".utf8))
    }

    func post<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        try await request(path, method: "POST", query: [], body: try encoder.encode(body))
    }

    func patch<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        try await request(path, method: "PATCH", query: [], body: try encoder.encode(body))
    }

    private func request<T: Decodable>(
        _ path: String,
        method: String,
        query: [URLQueryItem],
        body: Data?
    ) async throws -> T {
        guard var components = URLComponents(
            url: baseURL.appending(path: path),
            resolvingAgainstBaseURL: false
        ) else {
            throw APIError(message: "Invalid API URL.")
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError(message: "Invalid API URL.") }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "The backend returned an invalid response.")
        }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let message: String
            if let value = detail?["detail"] as? String {
                message = value
            } else if let value = detail?["detail"] as? [String: Any],
                      let nested = value["message"] as? String {
                message = nested
            } else if let values = detail?["detail"] as? [[String: Any]] {
                message = values.compactMap { $0["msg"] as? String }.joined(separator: "; ")
            } else {
                message = "Request failed (\(http.statusCode))."
            }
            throw APIError(message: message)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(message: "Could not read the backend response: \(error.localizedDescription)")
        }
    }
}
