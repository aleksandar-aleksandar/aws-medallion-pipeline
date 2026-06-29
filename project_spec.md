Here is the complete translation of your project specification into English, maintaining all technical terms, formatting, and structural details.

---

# Subject Project: Cloud Computing

The goal of this subject project is to implement a platform for collecting, processing, storing, and analyzing data from various social networks and blog portals. The solution must be implemented using the **AWS platform**. The data processing design must follow the **Medallion Architecture**.

## Functional Requirements

### 1. Data Collection (Bronze Layer)

It is required to collect data from 2 data sources (datasources): **Hacker News** and **X (Twitter)**.

#### 1.1. Hacker News Data Source

Hacker News is a portal for publishing blogs, news, and comments on various topics. It is necessary to collect all stories, asks, comments, jobs, and polls created on the previous day on a daily basis. The API is free, and the documentation is available [here]. The *HN Search API*, which searches the portal based on given keywords, can also be useful.

Data collection should be implemented using an **AWS Lambda function**. The function should write the collected data into an **S3 bucket** in its raw (native) format. No processing or data transformation is allowed at this stage, as the S3 bucket represents the Bronze Layer of the Data Lake, which is intended to store data in its original form.

#### 1.2. X (Twitter) Data Source

X (Twitter) is a social network for publishing short posts. Given that the free version of the X API is highly limited, you can use existing datasets on the Internet, or manually create/generate datasets. These datasets must be uploaded into the Data Lake bucket. Here are some examples of datasets that can be used (but are not mandatory): *Bitcoin Tweets*, *Covid Tweets*.

---

### 2. Data Normalization (Silver Layer)

Since the Bronze Layer of the Data Lake can contain data in different formats and the data structures themselves can vary, it is necessary to reduce this data to a unified format and form an appropriate data structure/schema. Without a defined data schema, queries cannot be written in later stages of data processing (queries cannot be written blindly). This process is called **data normalization**.

Implement a Lambda function (or functions) that will perform data normalization. Normalization includes:

* **Flattening nested structures** (e.g., `kids` fields in Hacker News posts).
* **Aligning timestamps**. Hacker News uses the Unix Epoch format (`1736978058`), while X uses ISO-8601 (`2026-01-15T21:54:18Z`). Timestamps need to be aligned into a single UTC format.
* **Data cleaning**. For example, some Hacker News posts contain HTML tags (`<p>`, `<i>`). These tags should be cleaned/removed.
* **Deduplication** (removing duplicates).
* **Additional data processing** that you deem necessary but is not explicitly listed above.
* **Establishing a data schema (structure)**. Define tables (dataframes) with their columns and the relationships between tables. As a rule, the schema should have minimal redundancy and satisfy **3NF** (Third Normal Form). Tables should be saved in **Parquet format** and the data must be **partitioned**.

The data structure setup is not unique and can differ depending on which data is interesting and beneficial to you. This data structure directly impacts later stages of data processing, and it is important to emphasize that it can change over time, especially if flaws in the schema are noticed.

A concrete example of an established data structure would consist of 2 tables:

* **`users`**
* `user_id`: UUID, generated ID
* `username`: String, extracted from the Hacker News and X platforms
* `platform`: String, `'Hacker News'` or `'X'`
* `karma_score`: Integer, user's reputation on Hacker News, `null` for X users
* `is_verified`: Boolean, whether the user is verified on X, `null` for Hacker News users
* `created_at`: Timestamp, normalized to UTC ISO-8601 format


* **`posts`**
* `post_id`: String, original ID from the Hacker News or X platform
* `author_username`: String, foreign key targeting the `users` table
* `content_text`: String, content of the post with HTML tags cleaned
* `created_at`: Timestamp, normalized to UTC ISO-8601 format
* `post_type`: String, `'story'`, `'comment'`, `'tweet'`, `'retweet'`



The `users` table would be partitioned by the `platform` column, while the `posts` table would be partitioned based on the timestamp column. In that case, the Data Lake bucket structure would look like this:

```text
s3://social-medias/silver/
 ├── posts/
 │    └── year=2026/month=01/day=15/
 │         └── data_001.parquet
 ├── users/
      ├── platform=HackerNews/
      └── platform=X/

```

For writing and reading in Parquet format, you can use the `awswrangler` library along with its Lambda Layer. A concrete example of data partitioning is available [here].

---

### 3. Data Transformation (Gold Layer)

Implement a Lambda function (or functions) that transforms the data and creates specific metrics and KPIs (Key Performance Indicators).

Calculate the following **metrics**:

* The daily count of created posts (`story`), questions (`asks`), comments (`comments`), job offers (`jobs`), and polls (`poll`) on the Hacker News portal.
* The number of active users from the Hacker News portal on a daily basis.
* The number of active users from the X platform on a daily basis.
* Top 10 X platform users with the largest number of followers.
* Top 10 Hacker News users with the highest karma score on a daily basis.
* Top 10 Hacker News users with the lowest karma score on a daily basis.
* Top 10 job offers on the Hacker News portal with the highest score on a daily basis.
* Top 10 posts on the Hacker News portal with the highest score on a daily basis.

Calculate the following **KPI**:

* **Data Quality Score**: Shows the percentage of rows in tables (dataframes) that are not `null`. This indicator shows how well the data normalization was performed.

You can use a **Star Schema** to design the data schema.

For example, to track the number of users on the platforms, the following table would be formed:

* **`daily_users_metric`**
* `date`: Date, the calendar date
* `platform`: String, `'Hacker News'` or `'X'`
* `total_users`: Integer, total number of users on a specific platform
* `new_users`: Integer, number of new users registered on that specific day and platform



| date | platform | total_users | new_users |
| --- | --- | --- | --- |
| 2025-01-15 | Hacker News | 11500 | 100 |
| 2025-01-15 | X | 456 | 74 |
| 2025-01-16 | Hacker News | 12030 | 530 |
| 2025-01-16 | X | 523 | 87 |

Partitioning would be done by the `platform` and `date` columns:

```text
s3://social-medias/gold/
 └── daily_users_metric/
      ├── platform=HackerNews/
      │    ├── date=2026-01-15/
      │    │    └── data_001.parquet
      │    └── date=2026-01-16/
      │         └── data_001.parquet
      └── platform=X/
           ├── date=2026-01-15/
           │    └── data_001.parquet
           └── date=2026-01-16/
                └── data_001.parquet

```

---

### 4. Data Visualization

Metrics and KPIs resulting from data transformation should be visualized using the **Apache Superset** tool. Since Apache Superset does not directly support visualizing data from S3 buckets in Parquet format, it is necessary to save the metrics and KPIs into a **PostgreSQL database**. Afterward, you must configure Apache Superset to read data from this PostgreSQL database.

Apache Superset and PostgreSQL should be hosted on an **EC2 instance**. Additionally, you must implement a Lambda function that moves metrics and KPIs from the S3 bucket into the PostgreSQL database on the EC2 instance.

### 5. Notifications

It is necessary to set up notifications sent to a **Discord server** for all jobs that fail or execute unsuccessfully. You may use another notification platform; using Discord is not mandatory.

**Data Processing Diagram Note:** You can use the **AWS Step Functions** service to split the normalization and transformation processes into multiple separate steps (i.e., separate Lambda functions), thereby simplifying the implementation of the functions themselves.

---

## Non-Functional Requirements

### 6. Infrastructure as Code (IaC)

All infrastructure must be written using an IaC tool: **CDK, CloudFormation, Terraform, or Terragrunt**.

> ⚠️ **Note:** Infrastructure as Code (IaC) is an elimination requirement. Projects that do not fulfill this requirement will not be graded.

### 7. Network Communication Control

The entire infrastructure must be implemented within a **VPC network**, applying the **principle of least privilege**. Only the minimum required network communication between services is allowed, enforced through security groups and network rules.

---

## Grading System

| Category | Points |
| --- | --- |
| 1. Data Collection (Bronze Layer) | 10 |
| 2. Data Normalization (Silver Layer) | 14 |
| 3. Data Transformation (Gold Layer) | 10 |
| 4. Data Visualization | 8 |
| 5. Notifications | 5 |
| 6. Network Communication Control | 3 |
| **Total** | **50** |

---

## Grading and Exam Rules

* The project is done in teams of **up to 3 members**.
* You can implement the project in any programming language and framework. If you choose a technology not covered during practical lab exercises (vežbe), assistant support will be limited.
* For all edge cases not explicitly covered in this specification, students are given the freedom to solve them in the manner they find most appropriate.
* The project is graded through a **checkpoint** held during the semester and a final **project defense** held during official exam periods (once in the June-July exam period and once in the August-September exam period).