idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS "."
                       REQUIRES lsm6dsv16x esp_driver_spi esp_driver_gpio freertos esp_timer)