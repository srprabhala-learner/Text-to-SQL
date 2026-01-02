import sqlite3

## Connect to SQLite
connection = sqlite3.connect("student.db")
cursor = connection.cursor()

## Drop existing tables if they exist (for clean setup)
cursor.execute("DROP TABLE IF EXISTS marks")
cursor.execute("DROP TABLE IF EXISTS teacher_subject_class")
cursor.execute("DROP TABLE IF EXISTS teachers")
cursor.execute("DROP TABLE IF EXISTS subjects")
cursor.execute("DROP TABLE IF EXISTS students")
cursor.execute("DROP VIEW IF EXISTS student_subject_status")

## Create Students Table
students_table = """
CREATE TABLE students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    class INTEGER NOT NULL,
    section VARCHAR(10) NOT NULL,
    roll_number VARCHAR(20) UNIQUE,
    date_of_birth DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, class, section, roll_number)
);
"""

## Create Subjects Table
subjects_table = """
CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name VARCHAR(100) NOT NULL UNIQUE,
    subject_code VARCHAR(20) UNIQUE,
    description TEXT
);
"""

## Create Teachers Table
teachers_table = """
CREATE TABLE teachers (
    teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    qualification VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

## Create Teacher-Subject-Class Mapping Table
## This allows teachers to teach specific subjects to specific class ranges
teacher_subject_class_table = """
CREATE TABLE teacher_subject_class (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    class_from INTEGER NOT NULL,
    class_to INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE CASCADE,
    CHECK (class_from <= class_to AND class_from >= 1 AND class_to <= 12)
);
"""

## Create Marks Table
## Stores marks for each student, subject, and semester
marks_table = """
CREATE TABLE marks (
    mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    marks_obtained DECIMAL(5,2) NOT NULL,
    max_marks DECIMAL(5,2) DEFAULT 100.00,
    percentage DECIMAL(5,2) GENERATED ALWAYS AS (marks_obtained * 100.0 / max_marks) STORED,
    is_final_semester BOOLEAN DEFAULT 0,
    exam_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE CASCADE,
    CHECK (semester >= 1 AND semester <= 2),
    CHECK (marks_obtained >= 0 AND marks_obtained <= max_marks),
    UNIQUE(student_id, subject_id, semester, is_final_semester)
);
"""

## Create View for Student Subject Status (Pass/Fail)
## Aggregate < 40% = FAIL
student_subject_status_view = """
CREATE VIEW student_subject_status AS
SELECT 
    s.student_id,
    s.name AS student_name,
    s.class,
    s.section,
    sub.subject_id,
    sub.subject_name,
    m.semester,
    m.is_final_semester,
    AVG(m.percentage) AS aggregate_percentage,
    CASE 
        WHEN AVG(m.percentage) < 40 THEN 'FAIL'
        ELSE 'PASS'
    END AS status
FROM students s
JOIN marks m ON s.student_id = m.student_id
JOIN subjects sub ON m.subject_id = sub.subject_id
GROUP BY s.student_id, sub.subject_id, m.semester, m.is_final_semester;
"""

## Execute table creation
cursor.execute(students_table)
cursor.execute(subjects_table)
cursor.execute(teachers_table)
cursor.execute(teacher_subject_class_table)
cursor.execute(marks_table)
cursor.execute(student_subject_status_view)

## Insert Sample Subjects
subjects_data = [
    ('Mathematics', 'MATH', 'Mathematics subject'),
    ('Science', 'SCI', 'Science subject including Physics, Chemistry, Biology'),
    ('Social Studies', 'SOC', 'Social Studies including History, Geography, Civics'),
    ('English', 'ENG', 'English Language and Literature'),
    ('Telugu', 'TEL', 'Telugu Language and Literature'),
    ('Computer Science', 'CS', 'Computer Science and Programming')
]

cursor.executemany('''INSERT INTO subjects (subject_name, subject_code, description) 
                      VALUES (?, ?, ?)''', subjects_data)

## Insert Sample Teachers
teachers_data = [
    ('Dr. Ramesh Kumar', 'ramesh.kumar@school.edu', '9876543210', 'Ph.D. in Mathematics'),
    ('Ms. Priya Sharma', 'priya.sharma@school.edu', '9876543211', 'M.Sc. Mathematics'),
    ('Dr. Anjali Reddy', 'anjali.reddy@school.edu', '9876543212', 'Ph.D. in Physics'),
    ('Mr. Suresh Patel', 'suresh.patel@school.edu', '9876543213', 'M.Sc. Chemistry'),
    ('Ms. Kavita Singh', 'kavita.singh@school.edu', '9876543214', 'M.A. History'),
    ('Mr. Rajesh Nair', 'rajesh.nair@school.edu', '9876543215', 'M.A. Geography'),
    ('Ms. Meera Das', 'meera.das@school.edu', '9876543216', 'M.A. English'),
    ('Mr. Vikram Rao', 'vikram.rao@school.edu', '9876543217', 'M.A. Telugu'),
    ('Dr. Arjun Mehta', 'arjun.mehta@school.edu', '9876543218', 'Ph.D. in Computer Science'),
    ('Ms. Deepika Iyer', 'deepika.iyer@school.edu', '9876543219', 'M.Tech. Computer Science'),
    ('Mr. Karthik Menon', 'karthik.menon@school.edu', '9876543220', 'B.Tech. Computer Science'),
    ('Ms. Sneha Nair', 'sneha.nair@school.edu', '9876543221', 'M.Tech. Computer Science'),
    ('Mr. Aditya Kumar', 'aditya.kumar@school.edu', '9876543222', 'B.Tech. Computer Science')
]

cursor.executemany('''INSERT INTO teachers (teacher_name, email, phone, qualification) 
                      VALUES (?, ?, ?, ?)''', teachers_data)

## Insert Teacher-Subject-Class Mappings
## Example: Some CS teachers teach up to class V, some only to class 10
teacher_subject_class_data = [
    # Mathematics teachers
    (1, 1, 1, 12),  # Dr. Ramesh Kumar teaches Math to all classes (1-12)
    (2, 1, 1, 10),  # Ms. Priya Sharma teaches Math up to class 10
    
    # Science teachers
    (3, 2, 1, 12),  # Dr. Anjali Reddy teaches Science to all classes
    (4, 2, 6, 12),  # Mr. Suresh Patel teaches Science from class 6-12
    
    # Social Studies teachers
    (5, 3, 1, 10),  # Ms. Kavita Singh teaches Social Studies up to class 10
    (6, 3, 1, 12),  # Mr. Rajesh Nair teaches Social Studies to all classes
    
    # English teachers
    (7, 4, 1, 12),  # Ms. Meera Das teaches English to all classes
    
    # Telugu teachers
    (8, 5, 1, 12),  # Mr. Vikram Rao teaches Telugu to all classes
    
    # Computer Science teachers - different class ranges
    (9, 6, 1, 12),   # Dr. Arjun Mehta teaches CS to all classes
    (10, 6, 1, 5),   # Ms. Deepika Iyer teaches CS up to class 5
    (11, 6, 6, 10),  # Mr. Karthik Menon teaches CS from class 6-10
    (12, 6, 11, 12), # Ms. Sneha Nair teaches CS for classes 11-12
    (13, 6, 1, 10)   # Mr. Aditya Kumar teaches CS up to class 10
]

cursor.executemany('''INSERT INTO teacher_subject_class (teacher_id, subject_id, class_from, class_to) 
                      VALUES (?, ?, ?, ?)''', teacher_subject_class_data)

## Insert Sample Students
students_data = [
    ('Rahul Sharma', 10, 'A', '10A001'),
    ('Priya Patel', 10, 'A', '10A002'),
    ('Amit Kumar', 10, 'B', '10B001'),
    ('Sneha Reddy', 9, 'A', '9A001'),
    ('Vikram Singh', 9, 'B', '9B001'),
    ('Anjali Nair', 8, 'A', '8A001'),
    ('Karthik Iyer', 7, 'A', '7A001'),
    ('Meera Das', 6, 'A', '6A001'),
    ('Arjun Menon', 5, 'A', '5A001'),
    ('Deepika Rao', 5, 'B', '5B001')
]

cursor.executemany('''INSERT INTO students (name, class, section, roll_number) 
                      VALUES (?, ?, ?, ?)''', students_data)

## Insert Sample Marks
## Example marks for different students, subjects, and semesters
marks_data = [
    # Rahul Sharma (student_id=1, class 10A) - Semester 1
    (1, 1, 1, 85, 100, 0, '2024-01-15'),  # Math
    (1, 2, 1, 78, 100, 0, '2024-01-16'),  # Science
    (1, 3, 1, 82, 100, 0, '2024-01-17'),  # Social Studies
    (1, 4, 1, 90, 100, 0, '2024-01-18'),  # English
    (1, 5, 1, 75, 100, 0, '2024-01-19'),  # Telugu
    (1, 6, 1, 88, 100, 0, '2024-01-20'),  # Computer Science
    
    # Rahul Sharma - Semester 2
    (1, 1, 2, 87, 100, 0, '2024-06-15'),  # Math
    (1, 2, 2, 80, 100, 0, '2024-06-16'),  # Science
    (1, 3, 2, 85, 100, 0, '2024-06-17'),  # Social Studies
    (1, 4, 2, 92, 100, 0, '2024-06-18'),  # English
    (1, 5, 2, 78, 100, 0, '2024-06-19'),  # Telugu
    (1, 6, 2, 90, 100, 0, '2024-06-20'),  # Computer Science
    
    # Priya Patel (student_id=2, class 10A) - Semester 1 (some failing marks)
    (2, 1, 1, 35, 100, 0, '2024-01-15'),  # Math - FAIL
    (2, 2, 1, 38, 100, 0, '2024-01-16'),  # Science - FAIL
    (2, 3, 1, 42, 100, 0, '2024-01-17'),  # Social Studies - PASS
    (2, 4, 1, 45, 100, 0, '2024-01-18'),  # English - PASS
    (2, 5, 1, 50, 100, 0, '2024-01-19'),  # Telugu - PASS
    (2, 6, 1, 55, 100, 0, '2024-01-20'),  # Computer Science - PASS
    
    # Priya Patel - Semester 2
    (2, 1, 2, 32, 100, 0, '2024-06-15'),  # Math - FAIL
    (2, 2, 2, 36, 100, 0, '2024-06-16'),  # Science - FAIL
    (2, 3, 2, 40, 100, 0, '2024-06-17'),  # Social Studies - PASS (borderline)
    (2, 4, 2, 48, 100, 0, '2024-06-18'),  # English - PASS
    (2, 5, 2, 52, 100, 0, '2024-06-19'),  # Telugu - PASS
    (2, 6, 2, 58, 100, 0, '2024-06-20'),  # Computer Science - PASS
    
    # Amit Kumar (student_id=3, class 10B) - Final Semester
    (3, 1, 2, 92, 100, 1, '2024-06-15'),  # Math - Final
    (3, 2, 2, 88, 100, 1, '2024-06-16'),  # Science - Final
    (3, 3, 2, 85, 100, 1, '2024-06-17'),  # Social Studies - Final
    (3, 4, 2, 95, 100, 1, '2024-06-18'),  # English - Final
    (3, 5, 2, 90, 100, 1, '2024-06-19'),  # Telugu - Final
    (3, 6, 2, 93, 100, 1, '2024-06-20'),  # Computer Science - Final
    
    # Sneha Reddy (student_id=4, class 9A) - Sample marks
    (4, 1, 1, 75, 100, 0, '2024-01-15'),
    (4, 2, 1, 72, 100, 0, '2024-01-16'),
    (4, 6, 1, 80, 100, 0, '2024-01-20'),
    
    # Arjun Menon (student_id=9, class 5A) - Sample marks (taught by different CS teacher)
    (9, 6, 1, 85, 100, 0, '2024-01-20'),  # CS - taught by Ms. Deepika Iyer (class 1-5)
]

cursor.executemany('''INSERT INTO marks (student_id, subject_id, semester, marks_obtained, max_marks, is_final_semester, exam_date) 
                      VALUES (?, ?, ?, ?, ?, ?, ?)''', marks_data)

## Display all records
print("\n" + "="*80)
print("STUDENTS TABLE")
print("="*80)
data = cursor.execute('''SELECT * FROM students''')
for row in data:
    print(row)

print("\n" + "="*80)
print("SUBJECTS TABLE")
print("="*80)
data = cursor.execute('''SELECT * FROM subjects''')
for row in data:
    print(row)

print("\n" + "="*80)
print("TEACHERS TABLE")
print("="*80)
data = cursor.execute('''SELECT * FROM teachers''')
for row in data:
    print(row)

print("\n" + "="*80)
print("TEACHER-SUBJECT-CLASS MAPPING")
print("="*80)
data = cursor.execute('''SELECT 
    tsc.mapping_id,
    t.teacher_name,
    s.subject_name,
    tsc.class_from,
    tsc.class_to
FROM teacher_subject_class tsc
JOIN teachers t ON tsc.teacher_id = t.teacher_id
JOIN subjects s ON tsc.subject_id = s.subject_id
ORDER BY s.subject_name, tsc.class_from''')
for row in data:
    print(row)

print("\n" + "="*80)
print("MARKS TABLE (Sample)")
print("="*80)
data = cursor.execute('''SELECT 
    m.mark_id,
    s.name AS student_name,
    sub.subject_name,
    m.semester,
    m.marks_obtained,
    m.max_marks,
    m.percentage,
    m.is_final_semester
FROM marks m
JOIN students s ON m.student_id = s.student_id
JOIN subjects sub ON m.subject_id = sub.subject_id
LIMIT 10''')
for row in data:
    print(row)

print("\n" + "="*80)
print("STUDENT SUBJECT STATUS (Pass/Fail) - View")
print("="*80)
data = cursor.execute('''SELECT 
    student_name,
    class,
    section,
    subject_name,
    semester,
    aggregate_percentage,
    status
FROM student_subject_status
WHERE aggregate_percentage < 40 OR aggregate_percentage >= 40
ORDER BY student_name, subject_name, semester
LIMIT 15''')
for row in data:
    print(row)

print("\n" + "="*80)
print("FAILED STUDENTS (Aggregate < 40%)")
print("="*80)
data = cursor.execute('''SELECT 
    student_name,
    class,
    section,
    subject_name,
    semester,
    ROUND(aggregate_percentage, 2) AS percentage,
    status
FROM student_subject_status
WHERE status = 'FAIL'
ORDER BY student_name, subject_name''')
for row in data:
    print(row)

## Commit your changes in the database
connection.commit()
print("\n" + "="*80)
print("✅ Database created successfully!")
print("="*80)
print("\nDatabase Schema:")
print("- students: Student records with class and section")
print("- subjects: All subjects offered in school")
print("- teachers: All teachers available")
print("- teacher_subject_class: Mapping of teachers to subjects and class ranges")
print("- marks: Marks for each student, subject, and semester")
print("- student_subject_status: View showing pass/fail status (aggregate < 40% = FAIL)")
print("\n" + "="*80)

connection.close()
