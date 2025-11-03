#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uvicorn

from src.di.container import DIContainer
from src.app.application import Application
from src.app.lifecycle import ApplicationLifecycle


def create_application() -> tuple[Application, ApplicationLifecycle]:
    """Фабрика для создания приложения"""
    container = DIContainer()
    application = Application(container)
    lifecycle = ApplicationLifecycle(container, application)

    # Регистрируем обработчики жизненного цикла
    @application.app.on_event("startup")
    async def startup_event():
        await lifecycle.startup()

    @application.app.on_event("shutdown")
    async def shutdown_event():
        await lifecycle.shutdown()

    return application, lifecycle


# Создаем экземпляр приложения
app_instance, lifecycle_instance = create_application()
app = app_instance.app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('PORT', '8080')),
        access_log=False,
        loop="asyncio",
        limit_max_requests=1000,
        timeout_notify=30,
        timeout_keep_alive=5
    )
