allprojects {
    repositories {
        // 国内网络优先走阿里云镜像（maven.google.com 不可达时兜底）
        maven("https://maven.aliyun.com/repository/google")
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/public")
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
// 老插件（如 app_settings）compileSdk 写死 33，与新版 androidx 依赖不兼容，统一抬到 36
// （必须在 evaluationDependsOn 之前注册，否则 :app 已求值会抛异常）
subprojects {
    afterEvaluate {
        val androidExt =
            extensions.findByName("android") as? com.android.build.gradle.BaseExtension
        if (androidExt != null) {
            val current =
                androidExt.compileSdkVersion?.removePrefix("android-")?.toIntOrNull() ?: 0
            if (current < 36) {
                androidExt.compileSdkVersion(36)
            }
        }
    }
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
