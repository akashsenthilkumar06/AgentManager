import SwiftUI

enum AppTheme {
    static let background = Color(red: 0.135, green: 0.14, blue: 0.15)
    static let sidebar = Color(red: 0.165, green: 0.17, blue: 0.18)
    static let surface = Color(red: 0.19, green: 0.195, blue: 0.205)
    static let raised = Color(red: 0.225, green: 0.23, blue: 0.24)
    static let border = Color.white.opacity(0.11)
    static let accent = Color(red: 0.92, green: 0.925, blue: 0.94)
    static let positive = Color(red: 0.38, green: 0.78, blue: 0.56)
    static let warning = Color(red: 1.0, green: 0.68, blue: 0.25)
    static let danger = Color(red: 1.0, green: 0.36, blue: 0.38)
    static let secondaryText = Color.white.opacity(0.62)
}

struct SurfaceModifier: ViewModifier {
    var padding: CGFloat = 18
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(AppTheme.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct LiquidGlassModifier: ViewModifier {
    let cornerRadius: CGFloat
    let interactive: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(macOS 26.0, *) {
            content.glassEffect(
                .regular
                    .tint(Color.white.opacity(0.025))
                    .interactive(interactive),
                in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            )
        } else {
            content
                .background(
                    .ultraThinMaterial,
                    in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .stroke(Color.white.opacity(0.11), lineWidth: 1)
                )
        }
    }
}

extension View {
    func surface(_ padding: CGFloat = 18) -> some View {
        modifier(SurfaceModifier(padding: padding))
    }

    func liquidGlass(
        cornerRadius: CGFloat = 16,
        interactive: Bool = false
    ) -> some View {
        modifier(
            LiquidGlassModifier(
                cornerRadius: cornerRadius,
                interactive: interactive
            )
        )
    }
}

struct StatusDot: View {
    let status: String
    var body: some View {
        Circle()
            .fill(status == "healthy" || status == "passed" || status == "verified"
                  ? AppTheme.positive
                  : status == "offline" || status == "failed"
                  ? AppTheme.danger
                  : AppTheme.warning)
            .frame(width: 7, height: 7)
    }
}

struct StatusPill: View {
    let status: String
    var body: some View {
        HStack(spacing: 6) {
            StatusDot(status: status)
            Text(status.replacingOccurrences(of: "_", with: " ").capitalized)
                .font(.caption.weight(.medium))
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(Color.white.opacity(0.055))
        .clipShape(Capsule())
    }
}

struct PageTitle: View {
    let eyebrow: String
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(eyebrow)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppTheme.accent)
            Text(title)
                .font(.system(size: 28, weight: .semibold))
            Text(detail)
                .font(.body)
                .foregroundStyle(AppTheme.secondaryText)
                .lineLimit(2)
        }
    }
}

extension String {
    var parsedDate: Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: self) ?? ISO8601DateFormatter().date(from: self)
    }

    var shortTimestamp: String {
        guard let date = parsedDate else { return self }
        return date.formatted(date: .abbreviated, time: .shortened)
    }
}
