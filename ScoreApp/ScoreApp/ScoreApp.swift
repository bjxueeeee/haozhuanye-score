//
//  ScoreApp.swift
//  ScoreApp
//
//  入口
//

import SwiftUI

@main
struct ScoreApp: App {
    var body: some Scene {
        WindowGroup {
            NavigationStack {
                ContentView()
                    .navigationBarTitleDisplayMode(.inline)
            }
        }
    }
}
