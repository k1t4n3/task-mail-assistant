-- Выполнить в pgAdmin один раз
-- CREATE TABLE в SQLAlchemy сделаем автоматически при старте (ниже), но это удобно для ручного наполнения.

INSERT INTO recipients (surname, full_name, email) VALUES
('шепырёв', 'Шепырёв Владимир Михайлович', 'shepyrevvladimir@gmail.com')
ON CONFLICT (surname) DO NOTHING;

INSERT INTO recipients (surname, full_name, email) VALUES
('петрова', 'Петрова Анна Сергеевна', 'petrova@company.ru')
ON CONFLICT (surname) DO NOTHING;

INSERT INTO recipients (surname, full_name, email) VALUES
('сидоров', 'Сидоров Сидор Сидорович', 'sidorov@company.ru')
ON CONFLICT (surname) DO NOTHING;