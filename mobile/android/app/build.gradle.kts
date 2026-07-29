import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val signingPropertiesPath =
    providers.environmentVariable("FAMILY_AI_ANDROID_SIGNING_PROPERTIES")
        .orNull
        ?.let(::file)
        ?: file("${System.getProperty("user.home")}/.family-ai/android-signing/key.properties")
val releaseSigningProperties = Properties()
val releaseSigningConfigured = signingPropertiesPath.isFile

if (releaseSigningConfigured) {
    signingPropertiesPath.inputStream().use(releaseSigningProperties::load)
}

fun requiredSigningProperty(name: String): String =
    releaseSigningProperties.getProperty(name)?.takeIf(String::isNotBlank)
        ?: throw GradleException(
            "Missing '$name' in external Android signing properties: $signingPropertiesPath",
        )

android {
    namespace = "ru.familyai.mentor"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "ru.familyai.mentor"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (releaseSigningConfigured) {
            create("release") {
                storeFile = file(requiredSigningProperty("storeFile"))
                storePassword = requiredSigningProperty("storePassword")
                keyAlias = requiredSigningProperty("keyAlias")
                keyPassword = requiredSigningProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig =
                if (releaseSigningConfigured) {
                    signingConfigs.getByName("release")
                } else {
                    null
                }
        }
    }
}

if (!releaseSigningConfigured) {
    tasks.configureEach {
        if (name.contains("release", ignoreCase = true)) {
            doFirst {
                throw GradleException(
                    "Release signing is not configured. Run " +
                        "scripts/mobile/Initialize-AndroidSigning.ps1 first.",
                )
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
