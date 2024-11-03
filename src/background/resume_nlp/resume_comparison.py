#(c) 2024 Daniel DeMoney. All rights reserved.
import re
import numpy as np
import time
import torch
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
from transformers import AutoTokenizer, AutoModel, AutoConfig
from sentence_transformers import util
import os
from openai import OpenAI
import asyncio
import json
from resume import Resume
from typing import Dict
from uuid import UUID
import logging

np.set_printoptions(threshold=np.inf)

CALCULATE_EMBEDDING_INFO=False

# Download NLTK stop words list if not already downloaded
class ResumeComparison:
    config = AutoConfig.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2", output_attentions=True)
    tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
    model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2", config=config)
    stop_words = set(stopwords.words('english'))

    def preprocess(text):
        # Step 1: Remove URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)

        # Step 2: Remove dates (various formats)
        text = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', text)  # e.g., 12/12/2024, 12-12-2024
        text = re.sub(r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b', '', text)  # e.g., 2024-12-12
        text = re.sub(r'\b\d{1,2} [A-Za-z]{3,9} \d{4}\b', '', text)  # e.g., 12 Dec 2024
        text = re.sub(r'\b[A-Za-z]{3,9} \d{1,2},? \d{4}\b', '', text)  # e.g., Dec 12, 2024
        # Step 3: Remove addresses (basic patterns, this can be extended)
        text = re.sub(r'\d{1,5} [A-Za-z0-9 ]+ (St|Street|Rd|Road|Ave|Avenue|Blvd|Boulevard|Ln|Lane|Dr|Drive)\b', '', text)
        text = re.sub(r'\b[A-Za-z0-9]+,\s*[A-Za-z]+\s*\d{5}(-\d{4})?\b', '', text)  # e.g., city, state zip code
        # Lowercase the text
        text = text.lower()

        # Remove special characters except for sentence boundary punctuation
        #text = re.sub(r'[^a-zA-Z0-9\s\.\!\?]', '', text)
        text = ' '.join([word for word in text.split() if word not in ResumeComparison.stop_words])
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text
    # Split text into sentences
    def split_into_sentences(text):
        # Split based on newlines first
        sentences = text.splitlines()
        refined_sentences = []
        for sentence in sentences:
            # Further split on punctuation
            refined_sentences.extend(re.split(r'[\.\?!;]', sentence))

        # Remove empty strings and strip whitespace
        refined_sentences = [s.strip() for s in refined_sentences if s.strip()]
        return refined_sentences

    def get_embeddings(text):
        def batch(iterable, n=1):
            length = len(iterable)
            for idx in range(0, length, n):
                yield iterable[idx:min(idx + n, length)]
        t1 = time.time()
        sentences = ResumeComparison.split_into_sentences(text)
        sentences = [ResumeComparison.preprocess(sentence) for sentence in sentences]

        embeddings_list = []

        for sentence_batch in batch(sentences, 32):
            inputs = ResumeComparison.tokenizer(sentence_batch, padding=True, truncation=True, return_tensors="pt")

            # Get the embeddings from the model
            with torch.no_grad():
                outputs = ResumeComparison.model(**inputs)
                hidden_states = outputs.last_hidden_state
                attention_weights = outputs.attentions[-1]

                # Average attention heads
                attention_weights = attention_weights.mean(dim=1)

                # Apply attention weights to hidden states
                weighted_hidden_states = torch.matmul(attention_weights, hidden_states)

                # Sum up the weighted hidden states for each token to get the final embedding
                embeddings = weighted_hidden_states.sum(dim=1)
                embeddings_list.append(embeddings)

        # Concatenate all embeddings
        final_embeddings = torch.cat(embeddings_list, dim=0)
        logging.info(f"Generating embeddings took {time.time() - t1}")
        return final_embeddings
    def get_similarity_matrix(job_description_text, resume_text):
        job_embeddings = ResumeComparison.get_embeddings(job_description_text)
        resume_embeddings = ResumeComparison.get_embeddings(resume_text)
        return util.pytorch_cos_sim(job_embeddings, resume_embeddings).cpu().numpy()
    def compare_embeddings(similarity_matrix):
        #exact matches are duds
        similarity_matrix[similarity_matrix > 0.95] = 0
        # Flatten the matrix and get indices sorted by values
        sorted_indices = np.argsort(similarity_matrix.flatten())[::-1]

        # Convert flattened index to 2D index
        sorted_indices_2d = np.unravel_index(sorted_indices, similarity_matrix.shape)

        # Zip row and column indices together
        sorted_index_list = list(zip(sorted_indices_2d[0], sorted_indices_2d[1]))

        return sorted_index_list
    def serialize_similarity_matrix(similarity_matrix):
        similarity_matrix_str = '\n'.join(' '.join(map(str, row)) for row in similarity_matrix)
        return similarity_matrix_str
    def serialize_sorted_index_list(sorted_index_list):
        sorted_index_list = [list(a) for a in sorted_index_list]
        sorted_index_numpy = np.array(sorted_index_list)
        return np.array2string(sorted_index_numpy, formatter={'float_kind': lambda x: f"{x:.3f}"})
    def clean_llm_text(text):
        t1 = time.time()
        text = text.lower().strip()
        text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
        text = ' '.join([word for word in text.split() if word not in ResumeComparison.stop_words])
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        lemmatizer = WordNetLemmatizer()
        words = text.split()
        lemmatized_words = [lemmatizer.lemmatize(word, wordnet.VERB) for word in words]
        print(f"Prepocessing llm took text took {time.time() - t1}")
        return ' '.join(lemmatized_words)
        #return text
    def calculate_llm_info(job_description: str, resume_text: str):
        # Assuming clean_llm_text is synchronous, otherwise make it async
        #job_description = ResumeComparison.clean_llm_text(job_description)
        #resume_text = ResumeComparison.clean_llm_text(resume_text)
        
        t1 = time.time()

        with OpenAI(api_key=os.environ["OPEN_AI_KEY"]) as client:
            # Make the API request asynchronous
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant skilled in evaluating resumes based on job descriptions."},
                    {"role": "user", "content": f'''Job Description: {job_description}\n\nResume: {resume_text}\n\n
                    Please compare this preprocessed resume to this preprocessed job description. Provide a match score from 0 to 100, ensuring that scores are spread evenly across the entire range (0-100), 
                    and avoid favoring numbers that end in 5 or 0 (e.g. 25, 30, 45).
                    List up to 3 pros and 3 cons of the resume, and suggest tips for improvement. For easy scraping please format your response as JSON, with the key to
                    match score being matchScore, the key to pros being pros and pros being an array, the key to cons being cons and cons being an array, and tips for improvement
                    having a key of tips and being an array.'''},
                ]
            )
            
            response_text = response.choices[0].message.content
            logging.debug(response_text)
            
            # Extract the JSON response
            startJsonIndex = response_text.find("{")
            endJsonIndex = response_text.rfind("}")
            response_json = json.loads(response_text[startJsonIndex:endJsonIndex+1])
        
        logging.info(f"Loading CHATGPT info took {time.time() - t1} seconds")
        return response_json
    def calculate_llm_info_match_score_only(job_description: str, resume_text: str):
        # Assuming clean_llm_text is synchronous, otherwise make it async
        job_description = ResumeComparison.clean_llm_text(job_description)
        resume_text = ResumeComparison.clean_llm_text(resume_text)
        
        t1 = time.time()

        with OpenAI(api_key=os.environ["OPEN_AI_KEY"]) as client:
            # Make the API request asynchronous
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a hiring manager evaluating resumes to the qualifications of job descriptions."},
                    {"role": "user", "content": f'''Job Description: {job_description}\n\nResume: {resume_text}\n\n
                    Please compare this preprocessed resume to this preprocessed job description. Provide a match score from 0 to 100, ensuring that scores are spread evenly across the entire range (0-100), and avoid favoring numbers that end in 5 or 0 (e.g. 25, 30, 45). 
                    For easy scraping please format your response as JSON, with the key to
                    match score being matchScore.'''},
                ]
            )
            
            response_text = response.choices[0].message.content
            logging.debug(response_text)
            
            # Extract the JSON response
            startJsonIndex = response_text.find("{")
            endJsonIndex = response_text.rfind("}")
            response_json = json.loads(response_text[startJsonIndex:endJsonIndex+1])
        
        logging.info(f"Loading CHATGPT info took {time.time() - t1} seconds")
        return response_json
    async def calculate_average_llm_info(job_description: str, resume_text: str):
        wordnet.ensure_loaded()
        # Use asyncio to run the synchronous `calculate_llm_info_match_score_only` in separate threads
        loop = asyncio.get_event_loop()

        # Run 4 instances of calculate_llm_info_match_score_only concurrently using threads
        tasks = [
            loop.run_in_executor(None, ResumeComparison.calculate_llm_info, job_description, resume_text),
            *(loop.run_in_executor(None, ResumeComparison.calculate_llm_info_match_score_only, job_description, resume_text) for _ in range(4))
        ]
        
        # Await all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Extract the matchScore from each result and calculate the average
        match_scores = [result["matchScore"] for result in results]
        average_score = int(sum(match_scores) / len(match_scores))
        
        logging.info(f"Average match score: {average_score}")
        main_dict = results[0]
        main_dict["matchScore"] = average_score
        return main_dict
    def get_embedding_comparison_dict(job_description: str, job_id: str, resume: Resume, user_id: str | UUID) -> Dict:
        logging.debug("Loaded job description")
        logging.debug(job_description)
        t1 = time.time()
        job_description_sentences: list[str] = ResumeComparison.split_into_sentences(job_description)
        logging.debug("Loaded job sentences")
        logging.debug(job_description_sentences)
        logging.debug("Created necessary items")
        logging.info(f"Splitting into sentences took {time.time() -t1} seconds")
        t2 = time.time()
        similarity_matrix = ResumeComparison.get_similarity_matrix(job_description, resume.file_text)
        logging.info(f"Loading similarity took {time.time() -t2} seconds")
        logging.debug("Loaded similarity matrix")
        t3 = time.time()
        sorted_index_list = ResumeComparison.compare_embeddings(similarity_matrix)
        logging.info(f"Loading sorted index list took {time.time() -t3} seconds")
        logging.debug("Loaded sorted index list")
        resume_sentences: list[str] = ResumeComparison.split_into_sentences(resume.file_text)
        resume_comparison_data: Dict = {
            "similarityMatrix": ResumeComparison.serialize_similarity_matrix(similarity_matrix),
            "sortedIndexList": ResumeComparison.serialize_sorted_index_list(sorted_index_list),
            "jobDescriptionSentences": job_description_sentences,
            "resumeSentences": resume_sentences
        }
        return resume_comparison_data
    def get_resume_comparison_dict(job_description: str, job_id: str, resume: Resume, user_id: str | UUID) -> Dict:
        resume_comparison_data = {
            "userId": str(user_id),
            "jobId": job_id,
            "resumeId": str(resume.id)
        }
        if CALCULATE_EMBEDDING_INFO:
            resume_comparison_data = ResumeComparison.get_embedding_comparison_dict(job_description, job_id, resume, user_id)
        llm_info = asyncio.run(ResumeComparison.calculate_average_llm_info(job_description, resume.file_text))
        resume_comparison_data.update(llm_info)
        return resume_comparison_data
    def print_comparisons(job_description, resume, max_num=60):
        job_sentences = ResumeComparison.split_into_sentences(job_description)
        resume_sentences = ResumeComparison.split_into_sentences(resume)
        similarity_matrix = ResumeComparison.get_similarity_matrix(job_description, resume)
        sorted_index_list = ResumeComparison.compare_embeddings(similarity_matrix)
        #only uncomment if necessary, money....
        #ResumeComparison.calculate_llm_info(job_description, resume)
        i=0
        seen_job_description_sentences = []
        seen_resume_sentences = []
        for (job_description_sentence_index, resume_sentence_index) in sorted_index_list:
            if resume_sentence_index in seen_resume_sentences or job_description_sentence_index in seen_job_description_sentences:
                continue
            seen_job_description_sentences.append(job_description_sentence_index)
            seen_resume_sentences.append(resume_sentence_index)
            print(f"================= NUMBER {i} ================")
            print("SENTENCES:")
            print(f"JOB DESCRIPTION SENTENCE: {job_sentences[job_description_sentence_index]}")
            print(f"RESUME DESCRIPTION SENTENCE: {resume_sentences[resume_sentence_index]}")
            print(f"VALUE: {similarity_matrix[job_description_sentence_index][resume_sentence_index]}")
            i += 1
            if i > max_num:
                break

job_description = '''
About the job
 ADP is hiring a Sales Representative, Human Resources Outsourcing (HRO).
 Are you ready for your next best job where you can elevate your financial future?
 Are you looking to grow your career with a formal career path at an established, respected, global leader?
 Do you want to join a fast-paced, inclusive environment with a culture of collaboration and belonging?
 If so, this may be the opportunity you've been searching for. Read on and decide for yourself.
 In this role, you will close sales and win new business within a defined territory. You'll attend our award-winning training program and join a sales team that works with both new and existing clients to sell human resources solutions, making employees' lives better with high-quality benefits offerings across the hire-to-retire spectrum. Daily, you will cultivate relationships with Human Resources and executive decision-makers, set appointments, gather leads from established internal partners, and assess buyer needs to present the best ADP solutions.
 You will use your ability to manage multiple sales processes at the same time through various stages in the sales process, as well as document them, sticking with the process through implementation until your new business is up and running on the solutions you sell. As you see more and more deals cross the finish line, you'll reap the rewards with industry-leading compensation, benefits, luxurious incentive trips, and awards. As you strive to grow your career, leaders will back your desire to pursue advancement and provide continual sales training.
 A little about ADP: We are a global leader in human resources technology, offering the latest AI and machine learning-enhanced payroll, tax, human resources, benefits, and much more. We believe our people make all the difference in cultivating an inclusive, down-to-earth culture that welcomes ideas, encourages innovation, and values belonging. We've received recognition as a global Best Places to Work and a recipient of many prestigious awards for diversity, equity, and inclusion, including a DiversityInc® Top 50 Company, Best CEO and company for women, LGBTQ+, multicultural talent, and more. As part of our deep DEI commitment, our CEO has joined the OneTen coalition to create one million jobs for Black Americans over the next ten years. Learn more about DEI at ADP on our YouTube channel: http://adp.careers/DEI_Videos.
 Ready to #MakeYourMark? Apply now!
 To learn more about Sales at ADP, watch here: http://adp.careers/Sales_Videos
 WHAT YOU'LL DO: Responsibilities
 Grow Our Business While Growing Yours: You will work within a defined, protected territory to close sales, win business, and reach sales goals by implementing a top-down sales strategy. 
 Turn Prospects into Loyal and Referring Clients: You will close sales by recommending the right solutions to help our clients understand and solve their real business needs. Plus, you'll earn referral business by networking with existing and soon-to-be clients and forging partnerships in-person and over the phone with decision-makers.
 Deepen Relationships Across the ADP Family: In addition to cloud-based human resources solutions, you will strategically cross-sell with other ADP associates to cultivate additional business within existing accounts; you will make life-long friendships here.
 Collaborate Daily. You will serve as a trusted advisor, partner, and ADP ambassador to your clients, internal partners, and overall network while demonstrating grace under pressure and the highest ethical standards.
 TO SUCCEED IN THIS ROLE: Required Qualifications
 Positive Self-Starter. You have an upbeat, persistent style and the ability to cold call without fear of rejection. You can manage your time well, prioritize deliverables, and multi-task with the best of them. In addition, you can present your ideas in a clear, professional manner on paper, in-person, and over the phone. 
 Strategic Closer. You have an established network and experience carrying a quota in outside business-to-business sales. You have an impressive track record of closing sales, winning clients, and managing a territory and relationships. 
 Proven Winner. You have an ambitious spirit and thrive under pressure, motivating you to not only hit sales quotas but exceed them.
 Required
 A college degree is great but not required. What's more important is having the skills to do the job. If you don't have a college degree, other acceptable experience could include:
 Three years of business-to-business sales experience (preferably field sales) within a results-driven environment.
 Military experience -- skills including teamwork, resilience, negotiation, trust-building, and a "never lose" mentality will help you build team and client relationships, identify solutions, and achieve success.
 Bonus points for these: Preferred Qualifications
 Ability to successfully build a network and effectively use social media for sales
 You'll Love Working Here Because You Can
 Be yourself in a culture that values equity, inclusion, and belonging and creates a safe space for diverse perspectives and insights.
 Belong by joining one of nine Business Resource Groups where you can connect globally with networks and allies who share common interests and experiences.
 Grow your career in an agile, fast-paced environment with plenty of opportunities to progress.
 Continuously learn. Ongoing training, development, and mentorship opportunities for even the most insatiable learner.
 Be your healthiest. Best-in-class benefits start on Day 1 because healthy associates are happy ones.
 Balance work and life. Resources and flexibility to more easily integrate your work and your life.
 Focus on your mental health and well-being. We're here to provide exceptional service to our clients, and none of that happens without each of us taking care of ourselves and being there for one another.
 Join a company committed to giving back and generating a lasting, positive impactupon the communities in which we work and live. 
 Get paid to pay it forward. Company-paid time off for volunteering for causes you care about.
 Base salary offers for this position may vary based on factors such as location, skills, and relevant experience.
 Some positions may include additional compensation in the form of bonus, equity or commissions.
 We offer the following benefits: Medical, Dental, Vision, Life Insurance, Matched Retirement Savings, Wellness
 Program, Short-and Long-Term Disability, Charitable Contribution Match, Holidays, Personal Days & Vacation,
 Paid Volunteer Time Off, and more.
 Compensation Range for this role is $42,400 - $92,000/ year
 What are you waiting for? Apply now!
 Base salary offers for this position may vary based on factors such as location, skills, and relevant experience. Some positions may include additional compensation in the form of bonus, equity or commissions. We offer the following benefits: Medical, Dental, Vision, Life Insurance, Matched Retirement Savings, Wellness Program, Short-and Long-Term Disability, Charitable Contribution Match, Holidays, Personal Days & Vacation, Paid Volunteer Time Off, and more. The compensation for this role is $42,400.00 - $92,000.00 / Year
 Diversity, Equity, Inclusion & Equal Employment Opportunity at ADP: ADP is committed to an inclusive, diverse and equitable workplace, and is further committed to providing equal employment opportunities regardless of any protected characteristic including: race, color, genetic information, creed, national origin, religion, sex, affectional or sexual orientation, gender identity or expression, lawful alien status, ancestry, age, marital status, protected veteran status or disability. Hiring decisions are based upon ADP’s operating needs, and applicant merit including, but not limited to, qualifications, experience, ability, availability, cooperation, and job performance.
 Ethics at ADP: ADP has a long, proud history of conducting business with the highest ethical standards and full compliance with all applicable laws. We also expect our people to uphold our values with the highest level of integrity and behave in a manner that fosters an honest and respectful workplace. Click https://jobs.adp.com/life-at-adp/ to learn more about ADP’s culture and our full set of values.
 '''
resume = '''
 Daniel DeMoney
 (408) 444-3650 • dandemoney@gmail.com •  Pomona, California 91768
 EXPERIENCE
 California Polytechnic Pomona, Consumer Insights Consultancy	Pomona, CA
 Consultant	Aug 2022 – May 2023
 	•	Collaborating with a small group of motivated students and faculty to create and execute a marketing research initiative to help a multi-million-dollar client increase profits.
 	•	Successfully prepared a research design to conduct market research on the client’s market.
 	•	Using machine learning techniques with R to gain insight from over a decade of transaction data.
 Coherent (formerly Finisar/II-VI)	San Jose, CA
 Sales Intern	May 2022 – Aug 2022
 	•	Worked closely with Sales Managers, Product Line Managers, and Senior VPs to execute deliverables on deals worth upwards of $10 million.
 	•	Helped lead an initiative to tabulate excess inventory into a database and sell pieces to brokers, netting over $1 million in revenue.
 	•	Created monthly forecasts using Demantra.
 	•	Conducted daily cold calls to prospect new clients.
 	•	Organized sales cycle data within Salesforce.
 California Polytechnic Pomona, Project Hatchery, Team Apollo	Pomona, CA
 Sales Lead	Aug 2021 – May 2022
 	•	Cofounded a team to develop and market a wearable blood pressure measurement device.
 	•	Helped allocate a $4,000 budget, develop project timelines, and program Bluetooth software for the prototype.
 Office Depot	Los Gatos, CA
 Sales Specialist	Aug 2020 – May 2021
 	•	Promoted to Sales Specialist from Sales Advisor within 2 months as a result of exceeding my quotas.
 	•	Gained experience selling and knowledge of Epson, Hp, Dell, and Microsoft products.
 	•	Oversaw the sales of laptops and desktop computers and increased tech bundle sales by 30%.
 	•	Lead the store in loyalty account signups for 6 months straight.
 EDUCATION
 California Polytechnic Pomona	Pomona, CA
 B.S. Business Marketing	May 2023
 REFERENCES
 Andres Gomez
 	•	Coherent, Former Account Manager 
 	•	(919) 943-8223, andres1.gomez@intel.com
 Stephen Cash
 	•	Coherent, Former Account Manager
 	•	(408) 813-8629, stephen.cash@gmail.com
'''
if __name__ == "__main__":
    ResumeComparison.print_comparisons(job_description, resume)
