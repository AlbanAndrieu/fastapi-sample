import os
from selenium import webdriver
from selenium.webdriver.common.by import By

USER_NAME = os.environ.get("USER_NAME", "alban.andrieu@gmail.com")
LOGIN_URL = os.environ.get("LOGIN_URL", "http://0.0.0.0:8091/auth/login")
USER_EMAIL = os.environ.get("USER_EMAIL", "your_app_password")

driver = webdriver.Chrome()
driver.get(LOGIN_URL)
driver.find_element(By.NAME, "username").send_keys(USER_NAME)
driver.find_element(By.NAME, "email").send_keys(USER_EMAIL)
driver.find_element(By.NAME, "submit").click()
